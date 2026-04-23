from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass
from pyueye import ueye
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum number of successfully captured frames required before the result
# is considered valid in multi-frame mode.  If fewer frames come back from
# the hardware (e.g. repeated is_FreezeVideo failures) we abort and return
# None so the caller can show a proper error instead of silently using a
# statistically unreliable average.
# ---------------------------------------------------------------------------
_MIN_USABLE_FRACTION = 0.5   # at least 50 % of requested frames must succeed
_MIN_FRAMES_FOR_REJECTION = 5  # need at least this many to run outlier logic


@dataclass
class FrameCaptureResult:
    """
    Immutable result object returned by capture_frame().

    Attributes
    ----------
    image : np.ndarray
        Pixel-wise averaged frame (BGR, uint8).  For n_frames=1 this is
        identical to the single captured frame.  Used for preview display
        and written to disk as the stored image file.
    gray_mean : float
        Outlier-cleaned arithmetic mean of per-frame grayscale values (0–255).
        This is the value that enters the Beer-Lambert calculation.
    gray_std : float
        Sample standard deviation of the per-frame grayscale values *after*
        outlier removal.  0.0 for single-frame captures.
        Stored in StdGrayRef / StdGraySample in the DB.
    frame_count : int
        Number of frames that were *requested*.
    frames_used : int
        Number of frames that were actually included in the average after
        outlier rejection.  frames_used <= frame_count.
    outliers_rejected : int
        Number of frames discarded by the sigma-clipping step.
    """
    image:             np.ndarray
    gray_mean:         float
    gray_std:          float
    frame_count:       int
    frames_used:       int
    outliers_rejected: int

    # Convenience -------------------------------------------------------
    @property
    def mode(self) -> str:
        """'multi' if more than one frame was requested, else 'single'."""
        return "multi" if self.frame_count > 1 else "single"

    @property
    def capture_ok(self) -> bool:
        """True when at least one frame was successfully used."""
        return self.frames_used > 0


# ---------------------------------------------------------------------------
# Helper – grayscale scalar without importing cv2 into the camera layer.
# Equivalent to cv2.cvtColor(img, COLOR_BGR2GRAY) → np.mean() because mean
# is a linear operator and cv2 uses the same ITU-R 601 coefficients.
# ---------------------------------------------------------------------------
def _bgr_frame_to_gray_scalar(frame: np.ndarray) -> float:
    """Return the mean luminance of a BGR uint8 frame as a float [0, 255]."""
    b = frame[:, :, 0].mean()
    g = frame[:, :, 1].mean()
    r = frame[:, :, 2].mean()
    return float(0.114 * b + 0.587 * g + 0.299 * r)


class CameraService:
    """
    Manages all interactions with the IDS uEye camera.

    Connection model
    ----------------
    The service does NOT connect on __init__.  Callers must explicitly
    call connect(camera_id) after listing available cameras.

    Capture model
    -------------
    capture_image()  – original single-frame API, returns np.ndarray | None.
                       Kept for full backward compatibility.
    capture_frame()  – new main API.  Accepts n_frames > 1 for multi-frame
                       averaging with sigma-clipping outlier rejection.
                       Returns FrameCaptureResult | None.
    """

    def __init__(self):
        self.h_cam            = ueye.HIDS(0)
        self.pc_image_memory  = ueye.c_mem_p()
        self.mem_id           = ueye.int()
        self.is_connected     = False
        self.width            = ueye.int()
        self.height           = ueye.int()
        self.model_name       = ""
        self.bits_per_pixel   = ueye.int(24)   # 8-bit BGR packed

    # ------------------------------------------------------------------
    # Camera discovery & lifecycle
    # ------------------------------------------------------------------

    def list_available_cameras(self) -> list[dict[str, Any]]:
        """Returns a list of connected uEye cameras that are not in use."""
        try:
            cam_list = ueye.UEYE_CAMERA_LIST()
            if ueye.is_GetCameraList(cam_list) != ueye.IS_SUCCESS:
                logger.error("Could not get camera list.")
                return []

            n_cameras = int(cam_list.dwCount)
            if n_cameras == 0:
                logger.info("No uEye cameras found.")
                return []

            result = []
            for i in range(n_cameras):
                cam_info = cam_list.uci[i]
                if cam_info.dwInUse == 0:
                    result.append({
                        "id":    int(cam_info.dwCameraID),
                        "model": cam_info.Model.decode("utf-8").strip("\x00").strip(),
                    })
            return result
        except Exception as e:
            logger.exception("Failed to list cameras: %s", e)
            return []

    def connect(self, camera_id: int) -> bool:
        """
        Disconnects any active camera, then initialises the requested one.
        Returns True on success.
        """
        if self.is_connected:
            self.disconnect()

        self.h_cam = ueye.HIDS(camera_id)

        if ueye.is_InitCamera(self.h_cam, None) != ueye.IS_SUCCESS:
            logger.error("Camera %s init failed.", camera_id)
            self.h_cam = ueye.HIDS(0)
            return False

        sensor_info = ueye.SENSORINFO()
        ueye.is_GetSensorInfo(self.h_cam, sensor_info)
        self.width      = sensor_info.nMaxWidth
        self.height     = sensor_info.nMaxHeight
        self.model_name = sensor_info.strSensorName.decode("utf-8").strip()

        if ueye.is_SetColorMode(self.h_cam, ueye.IS_CM_BGR8_PACKED) != ueye.IS_SUCCESS:
            logger.error("Failed to set color mode.")
            self.disconnect(); return False

        if ueye.is_SetDisplayMode(self.h_cam, ueye.IS_SET_DM_DIB) != ueye.IS_SUCCESS:
            logger.error("Failed to set display mode (DIB).")
            self.disconnect(); return False

        if ueye.is_AllocImageMem(self.h_cam, self.width, self.height,
                                  self.bits_per_pixel,
                                  self.pc_image_memory, self.mem_id) != ueye.IS_SUCCESS:
            logger.error("Image memory allocation failed.")
            self.disconnect(); return False

        if ueye.is_SetImageMem(self.h_cam, self.pc_image_memory,
                                self.mem_id) != ueye.IS_SUCCESS:
            logger.error("Failed to set active image memory.")
            self.disconnect(); return False

        self.is_connected = True
        logger.info("Camera %s (%s) ready (%sx%s px).",
                    camera_id, self.model_name,
                    self.width.value, self.height.value)
        return True

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "model":     self.model_name,
            "width":     self.width.value  if self.is_connected else 0,
            "height":    self.height.value if self.is_connected else 0,
        }

    def disconnect(self):
        if self.h_cam.value == 0:
            return
        if self.is_connected:
            ueye.is_StopLiveVideo(self.h_cam, ueye.IS_WAIT)
            if self.pc_image_memory.value:
                ueye.is_FreeImageMem(self.h_cam, self.pc_image_memory, self.mem_id)
            ueye.is_ExitCamera(self.h_cam)
        logger.info("Camera %s disconnected.", self.h_cam.value)
        self.h_cam           = ueye.HIDS(0)
        self.pc_image_memory = ueye.c_mem_p()
        self.mem_id          = ueye.int()
        self.is_connected    = False
        self.width           = ueye.int()
        self.height          = ueye.int()
        self.model_name      = ""

    def __del__(self):
        self.disconnect()

    # ------------------------------------------------------------------
    # Low-level hardware capture (private)
    # ------------------------------------------------------------------

    def _read_raw_frame(self) -> np.ndarray | None:
        """
        Triggers one hardware exposure via is_FreezeVideo and reads the
        resulting frame from camera memory into a numpy array.

        This is the single shared low-level primitive used by both
        capture_image() and capture_frame().
        """
        ret = ueye.is_FreezeVideo(self.h_cam, ueye.IS_WAIT)
        if ret != ueye.IS_SUCCESS:
            logger.error("is_FreezeVideo failed. Code: %s", ret)
            return None
        try:
            bpp        = int(self.bits_per_pixel.value / 8)
            w, h       = self.width.value, self.height.value
            raw        = ueye.get_data(self.pc_image_memory, w, h,
                                       self.bits_per_pixel, w * bpp, True)
            return np.reshape(raw, (h, w, bpp)).copy()
        except Exception as e:
            logger.exception("Failed to read frame from camera memory: %s", e)
            return None

    # ------------------------------------------------------------------
    # Public capture API
    # ------------------------------------------------------------------

    def capture_image(self) -> np.ndarray | None:
        """
        Original single-frame API.  Returns the raw BGR frame as a numpy
        array, or None on failure.

        Kept for full backward compatibility — existing callers are not
        broken before Step 4 updates the measure page.
        """
        if not self.is_connected:
            logger.error("capture_image: camera not connected.")
            return None
        return self._read_raw_frame()

    def capture_frame(
        self,
        n_frames:      int   = 1,
        outlier_sigma: float = 3.0,
    ) -> FrameCaptureResult | None:
        """
        Capture one or more frames and return a FrameCaptureResult.

        Single-frame mode (n_frames == 1)
        ----------------------------------
        Captures one frame.  gray_std = 0.0, frames_used = 1,
        outliers_rejected = 0.  Equivalent to capture_image() but wrapped
        in the richer return type.

        Multi-frame mode (n_frames > 1)
        --------------------------------
        1. Captures n_frames frames sequentially via is_FreezeVideo.
        2. Computes a grayscale scalar per frame using the ITU-R 601
           luminance formula (no cv2 dependency in this layer).
        3. Sigma-clipping outlier rejection (only when >= _MIN_FRAMES_FOR_REJECTION
           frames were collected):
           - Computes mean µ and std σ of the per-frame gray values.
           - Discards frames where |gray_i - µ| > outlier_sigma * σ.
           - If σ == 0 (all frames identical) no frames are rejected.
           - Safety net: if ALL frames would be rejected, uses all of them.
        4. Pixel-wise averages the kept frames into a single representative
           image (float32 accumulation → uint8).
        5. Returns statistics on the cleaned distribution.

        Returns None if:
        - Camera is not connected.
        - Fewer than _MIN_USABLE_FRACTION of requested frames could be
          read from hardware (repeated is_FreezeVideo failures).

        Args:
            n_frames:      Number of frames to capture and average.
                           Default 1 (single-frame mode).
            outlier_sigma: Frames whose gray value deviates more than this
                           many standard deviations from the mean are
                           rejected.  Default 3.0.
        """
        if not self.is_connected:
            logger.error("capture_frame: camera not connected.")
            return None

        # ── Single-frame fast path ──────────────────────────────────────
        if n_frames == 1:
            raw = self._read_raw_frame()
            if raw is None:
                return None
            gray = _bgr_frame_to_gray_scalar(raw)
            return FrameCaptureResult(
                image             = raw,
                gray_mean         = gray,
                gray_std          = 0.0,
                frame_count       = 1,
                frames_used       = 1,
                outliers_rejected = 0,
            )

        # ── Multi-frame path ────────────────────────────────────────────
        logger.info("Multi-frame capture: requesting %d frames (σ=%.1f).",
                    n_frames, outlier_sigma)

        raw_frames:   list[np.ndarray] = []
        gray_scalars: list[float]      = []

        for i in range(n_frames):
            raw = self._read_raw_frame()
            if raw is None:
                logger.warning("Frame %d/%d: hardware read failed, skipping.",
                               i + 1, n_frames)
                continue
            raw_frames.append(raw)
            gray_scalars.append(_bgr_frame_to_gray_scalar(raw))

        n_captured = len(raw_frames)
        logger.info("Multi-frame: %d/%d frames captured successfully.",
                    n_captured, n_frames)

        # Abort if too few frames came back from hardware
        if n_captured < max(1, int(n_frames * _MIN_USABLE_FRACTION)):
            logger.error(
                "Multi-frame: only %d/%d frames captured — below minimum "
                "usable threshold (%.0f %%). Aborting.",
                n_captured, n_frames, _MIN_USABLE_FRACTION * 100,
            )
            return None

        # ── Outlier rejection ──────────────────────────────────────────
        kept_frames  = raw_frames
        kept_grays   = gray_scalars
        n_outliers   = 0

        if n_captured >= _MIN_FRAMES_FOR_REJECTION:
            gray_arr = np.array(gray_scalars, dtype=np.float64)
            mu       = gray_arr.mean()
            sigma    = gray_arr.std()

            if sigma > 0:
                keep_mask = np.abs(gray_arr - mu) <= outlier_sigma * sigma
                n_kept    = int(keep_mask.sum())

                if n_kept > 0:            # safety: never reject everything
                    kept_frames = [f for f, k in zip(raw_frames, keep_mask) if k]
                    kept_grays  = gray_arr[keep_mask].tolist()
                    n_outliers  = n_captured - n_kept
                    if n_outliers > 0:
                        logger.info(
                            "Multi-frame: rejected %d outlier frame(s) "
                            "(sigma threshold = %.1f).",
                            n_outliers, outlier_sigma,
                        )
                else:
                    logger.warning(
                        "Multi-frame: sigma-clipping would reject ALL frames "
                        "— using all %d frames instead.", n_captured
                    )
            else:
                logger.debug("Multi-frame: σ = 0, all frames identical — no rejection.")

        # ── Pixel-wise average ─────────────────────────────────────────
        # Accumulate as float32, then convert back to uint8.
        accumulator = np.zeros_like(kept_frames[0], dtype=np.float32)
        for frame in kept_frames:
            accumulator += frame.astype(np.float32)
        avg_frame = (accumulator / len(kept_frames)).astype(np.uint8)

        # ── Statistics on cleaned distribution ────────────────────────
        clean_arr  = np.array(kept_grays, dtype=np.float64)
        gray_mean  = float(clean_arr.mean())
        gray_std   = float(clean_arr.std(ddof=1)) if len(clean_arr) > 1 else 0.0

        logger.info(
            "Multi-frame result: frames_used=%d, outliers=%d, "
            "gray_mean=%.3f, gray_std=%.3f",
            len(kept_frames), n_outliers, gray_mean, gray_std,
        )

        return FrameCaptureResult(
            image             = avg_frame,
            gray_mean         = gray_mean,
            gray_std          = gray_std,
            frame_count       = n_frames,
            frames_used       = len(kept_frames),
            outliers_rejected = n_outliers,
        )