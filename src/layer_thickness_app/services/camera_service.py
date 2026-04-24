from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass
from pyueye import ueye
from typing import Any

logger = logging.getLogger(__name__)

# At least 50 % of the requested frames must come back from the hardware
# before a multi-frame capture is considered valid.
_MIN_USABLE_FRACTION     = 0.5
_MIN_FRAMES_FOR_REJECTION = 5   # below this, skip sigma-clipping


@dataclass
class FrameCaptureResult:
    """
    Immutable result object returned by capture_frame().

    Attributes
    ----------
    image             : BGR uint8, pixel-wise averaged frame.
    gray_mean         : outlier-cleaned mean of per-frame gray scalars.
    gray_std          : sample std of per-frame gray scalars after outlier
                        rejection (0.0 for single-frame captures).
    frame_count       : number of frames requested.
    frames_used       : number of frames kept after outlier rejection.
    outliers_rejected : number of frames discarded by sigma-clipping.
    """
    image:             np.ndarray
    gray_mean:         float
    gray_std:          float
    frame_count:       int
    frames_used:       int
    outliers_rejected: int

    @property
    def mode(self) -> str:
        return "multi" if self.frame_count > 1 else "single"

    @property
    def capture_ok(self) -> bool:
        return self.frames_used > 0


def _bgr_frame_to_gray_scalar(frame: np.ndarray) -> float:
    """Mean luminance of a BGR uint8 frame (ITU-R 601, no cv2 dependency)."""
    b = frame[:, :, 0].mean()
    g = frame[:, :, 1].mean()
    r = frame[:, :, 2].mean()
    return float(0.114 * b + 0.587 * g + 0.299 * r)


class CameraService:
    """
    Manages interactions with the IDS uEye camera.

    Connection is explicit — the service does NOT connect on __init__.
    Callers must list available cameras and then call connect(camera_id).

    capture_frame(n_frames) is the single public capture API. n_frames=1
    takes one frame; n_frames>1 captures n frames, sigma-clips outliers,
    and returns the pixel-wise average along with statistics.
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
        """Disconnects any active camera, then initialises the requested one."""
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
        """Trigger one exposure and copy the frame from camera memory."""
        ret = ueye.is_FreezeVideo(self.h_cam, ueye.IS_WAIT)
        if ret != ueye.IS_SUCCESS:
            logger.error("is_FreezeVideo failed. Code: %s", ret)
            return None
        try:
            bpp  = int(self.bits_per_pixel.value / 8)
            w, h = self.width.value, self.height.value
            raw  = ueye.get_data(self.pc_image_memory, w, h,
                                 self.bits_per_pixel, w * bpp, True)
            return np.reshape(raw, (h, w, bpp)).copy()
        except Exception as e:
            logger.exception("Failed to read frame from camera memory: %s", e)
            return None

    # ------------------------------------------------------------------
    # Public capture API
    # ------------------------------------------------------------------

    def capture_frame(
        self,
        n_frames:      int   = 1,
        outlier_sigma: float = 3.0,
    ) -> FrameCaptureResult | None:
        """
        Capture one or more frames and return a FrameCaptureResult.

        Single-frame (n_frames == 1)
            Returns a single frame wrapped in the richer return type.
        Multi-frame (n_frames > 1)
            Captures n frames, sigma-clips outlier gray scalars, averages
            the kept frames pixel-wise (vectorised), and returns the
            cleaned statistics.

        Returns None if the camera is not connected, or if fewer than
        _MIN_USABLE_FRACTION of the requested frames came back from
        hardware.
        """
        if not self.is_connected:
            logger.error("capture_frame: camera not connected.")
            return None

        # Single-frame fast path
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

        # Multi-frame path
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

        if n_captured < max(1, int(n_frames * _MIN_USABLE_FRACTION)):
            logger.error(
                "Multi-frame: only %d/%d frames captured — below minimum "
                "usable threshold (%.0f %%). Aborting.",
                n_captured, n_frames, _MIN_USABLE_FRACTION * 100,
            )
            return None

        # Outlier rejection (sigma-clipping)
        kept_frames = raw_frames
        kept_grays  = gray_scalars
        n_outliers  = 0

        if n_captured >= _MIN_FRAMES_FOR_REJECTION:
            gray_arr = np.array(gray_scalars, dtype=np.float64)
            mu       = gray_arr.mean()
            sigma    = gray_arr.std()

            if sigma > 0:
                keep_mask = np.abs(gray_arr - mu) <= outlier_sigma * sigma
                n_kept    = int(keep_mask.sum())
                if n_kept > 0:
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
                        "— using all %d frames instead.", n_captured,
                    )
            else:
                logger.debug("Multi-frame: σ = 0, all frames identical — no rejection.")

        # Vectorised pixel-wise average.
        stack     = np.stack(kept_frames).astype(np.float32)   # (N, H, W, 3)
        avg_frame = stack.mean(axis=0).astype(np.uint8)

        clean_arr = np.array(kept_grays, dtype=np.float64)
        gray_mean = float(clean_arr.mean())
        gray_std  = float(clean_arr.std(ddof=1)) if len(clean_arr) > 1 else 0.0

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