from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass
from pyueye import ueye
from typing import Any

from layer_thickness_app.services.image_stats import compute_image_stats

logger = logging.getLogger(__name__)

_MIN_USABLE_FRACTION      = 0.5
_MIN_FRAMES_FOR_REJECTION = 5


@dataclass
class FrameCaptureResult:
    """
    Result of a (possibly multi-frame) capture.

    ``gray_mean`` / ``gray_std`` are the per-frame ITU-R 601 luminance
    statistics used for outlier rejection and Beer-Lambert. The remaining
    fields describe the *averaged* image and feed the plausibility gate:

    gray_p99           : 99th percentile of luminance (saturation tail).
    hotspot_mean       : mean over the top 0.5 % brightest pixels —
                         robust estimator of the laser spot intensity,
                         valid whether the spot fills the frame (thin
                         layer) or shrinks to a point (thick layer).
    saturated_fraction : fraction of pixels at or above 254 — detects
                         clipping even when most of the frame is dark.
    """
    image:              np.ndarray
    gray_mean:          float
    gray_std:           float
    gray_p99:           float
    hotspot_mean:       float
    saturated_fraction: float
    frame_count:        int
    frames_used:        int
    outliers_rejected:  int

    @property
    def mode(self) -> str:
        return "multi" if self.frame_count > 1 else "single"

    @property
    def capture_ok(self) -> bool:
        return self.frames_used > 0


def _bgr_frame_to_gray_scalar(frame: np.ndarray) -> float:
    """ITU-R 601 luminance of a BGR uint8 frame."""
    b = frame[:, :, 0].mean()
    g = frame[:, :, 1].mean()
    r = frame[:, :, 2].mean()
    return float(0.114 * b + 0.587 * g + 0.299 * r)


class CameraService:
    """
    IDS uEye camera wrapper.

    Connection is explicit: callers must list available cameras and then
    call connect(camera_id). capture_frame(n_frames) is the single public
    capture API; n_frames=1 takes one frame, n_frames>1 captures n
    frames, sigma-clips outliers, and returns the pixel-wise average plus
    statistics.
    """

    def __init__(self):
        self.h_cam            = ueye.HIDS(0)
        self.pc_image_memory  = ueye.c_mem_p()
        self.mem_id           = ueye.int()
        self.is_connected     = False
        self.width            = ueye.int()
        self.height           = ueye.int()
        self.model_name       = ""
        self.bits_per_pixel   = ueye.int(24)

    # ------------------------------------------------------------------
    # Camera discovery and lifecycle
    # ------------------------------------------------------------------

    def list_available_cameras(self) -> list[dict[str, Any]]:
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

        # Auto-shutter must be off: reference and sample frames need a
        # constant exposure for the I/I0 ratio to be meaningful. If the
        # call fails we still continue, but log loudly because the
        # measurements may then be inconsistent.
        self._disable_auto_exposure()

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
    # Exposure control
    # ------------------------------------------------------------------
    #
    # Wraps the IDS uEye is_Exposure() call. All values are in
    # milliseconds (the unit the SDK uses internally). The hardware
    # quantises the requested value to the increment reported by
    # get_exposure_range_ms(); set_exposure_ms() returns the actual
    # value that was applied.
    #
    # Auto-shutter is disabled in connect(). Do not re-enable it: a
    # constant exposure between reference and sample is required for
    # Beer-Lambert to produce a meaningful transmission ratio.

    def _disable_auto_exposure(self) -> None:
        enable = ueye.double(0.0)   # 0 = disabled
        rval   = ueye.double(0.0)   # not used for SET, but required arg
        ret = ueye.is_SetAutoParameter(
            self.h_cam, ueye.IS_SET_ENABLE_AUTO_SHUTTER, enable, rval,
        )
        if ret != ueye.IS_SUCCESS:
            logger.warning(
                "Could not disable auto-exposure (code %s); "
                "transmission measurements may be inconsistent.", ret,
            )
            return
        logger.info("Auto-exposure disabled.")

    def get_exposure_ms(self) -> float | None:
        """Current exposure time in milliseconds, or None on error."""
        if not self.is_connected:
            return None
        exp = ueye.double()
        ret = ueye.is_Exposure(
            self.h_cam, ueye.IS_EXPOSURE_CMD_GET_EXPOSURE,
            exp, ueye.sizeof(exp),
        )
        if ret != ueye.IS_SUCCESS:
            logger.error("Could not read exposure (code %s).", ret)
            return None
        return float(exp.value)

    def get_exposure_range_ms(self) -> tuple[float, float, float] | None:
        """Supported exposure range as (min, max, increment) in ms."""
        if not self.is_connected:
            return None
        cmds = (
            ueye.IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE_MIN,
            ueye.IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE_MAX,
            ueye.IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE_INC,
        )
        out: list[float] = []
        for cmd in cmds:
            v = ueye.double()
            ret = ueye.is_Exposure(self.h_cam, cmd, v, ueye.sizeof(v))
            if ret != ueye.IS_SUCCESS:
                logger.error(
                    "Could not read exposure range (cmd=%s, code=%s).",
                    cmd, ret,
                )
                return None
            out.append(float(v.value))
        return out[0], out[1], out[2]

    def set_exposure_ms(self, value_ms: float) -> float | None:
        """
        Set exposure time in milliseconds.

        The hardware rounds to the nearest valid step (the ``increment``
        from ``get_exposure_range_ms``). Returns the actual value that
        was applied, or None on failure. Out-of-range values are clamped
        to [min, max] with a warning rather than rejected.
        """
        if not self.is_connected:
            logger.error("set_exposure_ms: camera not connected.")
            return None

        rng = self.get_exposure_range_ms()
        if rng is not None:
            lo, hi, _inc = rng
            if value_ms < lo or value_ms > hi:
                clamped = max(lo, min(hi, value_ms))
                logger.warning(
                    "set_exposure_ms: %.4f ms outside [%.4f, %.4f]; "
                    "clamping to %.4f ms.",
                    value_ms, lo, hi, clamped,
                )
                value_ms = clamped

        target = ueye.double(value_ms)
        ret = ueye.is_Exposure(
            self.h_cam, ueye.IS_EXPOSURE_CMD_SET_EXPOSURE,
            target, ueye.sizeof(target),
        )
        if ret != ueye.IS_SUCCESS:
            logger.error(
                "set_exposure_ms: hardware rejected %.4f ms (code %s).",
                value_ms, ret,
            )
            return None

        actual = self.get_exposure_ms()
        if actual is None:
            actual = value_ms
        logger.info(
            "Exposure set: requested %.4f ms, applied %.4f ms.",
            value_ms, actual,
        )
        return actual

    # ------------------------------------------------------------------
    # Low-level hardware capture
    # ------------------------------------------------------------------

    def _read_raw_frame(self) -> np.ndarray | None:
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
        wavelength_um: float = 0.635,
    ) -> FrameCaptureResult | None:
        """
        Capture one or more frames and return a FrameCaptureResult.

        Single-frame fast path is taken when ``n_frames == 1``. For
        n_frames > 1 the gray scalar of each frame is sigma-clipped, the
        kept frames are averaged pixel-wise, and the cleaned statistics
        are returned. Returns None if the camera is not connected, or if
        fewer than _MIN_USABLE_FRACTION of the requested frames came
        back from hardware.

        ``wavelength_um`` selects the Bayer channel used for the hotspot
        statistic (635 nm → red, 532 nm → green). Whole-frame gray
        statistics are wavelength-independent and always use ITU-R 601.
        """
        if not self.is_connected:
            logger.error("capture_frame: camera not connected.")
            return None

        if n_frames == 1:
            raw = self._read_raw_frame()
            if raw is None:
                return None
            gray = _bgr_frame_to_gray_scalar(raw)
            stats = compute_image_stats(raw, wavelength_um=wavelength_um)
            return FrameCaptureResult(
                image              = raw,
                gray_mean          = gray,
                gray_std           = 0.0,
                gray_p99           = stats.gray_p99,
                hotspot_mean       = stats.hotspot_mean,
                saturated_fraction = stats.saturated_fraction,
                frame_count        = 1,
                frames_used        = 1,
                outliers_rejected  = 0,
            )

        logger.info("Multi-frame capture: requesting %d frames (sigma=%.1f).",
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
                "Multi-frame: only %d/%d frames captured -- below minimum "
                "usable threshold (%.0f %%). Aborting.",
                n_captured, n_frames, _MIN_USABLE_FRACTION * 100,
            )
            return None

        keep_mask = np.ones(n_captured, dtype=bool)
        n_outliers = 0

        if n_captured >= _MIN_FRAMES_FOR_REJECTION:
            gray_arr = np.asarray(gray_scalars, dtype=np.float64)
            mu       = gray_arr.mean()
            sigma    = gray_arr.std()

            if sigma > 0:
                candidate = np.abs(gray_arr - mu) <= outlier_sigma * sigma
                if candidate.any():
                    keep_mask  = candidate
                    n_outliers = int(n_captured - keep_mask.sum())
                    if n_outliers:
                        logger.info(
                            "Multi-frame: rejected %d outlier frame(s) "
                            "(sigma threshold = %.1f).",
                            n_outliers, outlier_sigma,
                        )
                else:
                    logger.warning(
                        "Multi-frame: sigma-clipping would reject ALL frames; "
                        "using all %d frames instead.", n_captured,
                    )
            else:
                logger.debug("Multi-frame: sigma = 0, all frames identical.")

        # Incremental float32 accumulator avoids an N*H*W*3 stack.
        accumulator: np.ndarray | None = None
        n_kept = 0
        kept_grays: list[float] = []
        for frame, gray, keep in zip(raw_frames, gray_scalars, keep_mask):
            if not keep:
                continue
            if accumulator is None:
                accumulator = frame.astype(np.float32)
            else:
                accumulator += frame
            n_kept += 1
            kept_grays.append(gray)

        if accumulator is None or n_kept == 0:
            logger.error("Multi-frame: no frames left after rejection.")
            return None

        avg_frame = (accumulator / float(n_kept)).astype(np.uint8)

        clean_arr = np.asarray(kept_grays, dtype=np.float64)
        gray_mean = float(clean_arr.mean())
        gray_std  = float(clean_arr.std(ddof=1)) if n_kept > 1 else 0.0

        # Spatial stats on the averaged image — this is what plausibility
        # and any downstream user inspection actually see.
        stats = compute_image_stats(avg_frame, wavelength_um=wavelength_um)

        logger.info(
            "Multi-frame result: frames_used=%d, outliers=%d, "
            "gray_mean=%.3f, gray_std=%.3f, hotspot_mean=%.3f, "
            "p99=%.3f, sat_frac=%.4f",
            n_kept, n_outliers, gray_mean, gray_std,
            stats.hotspot_mean, stats.gray_p99, stats.saturated_fraction,
        )

        return FrameCaptureResult(
            image              = avg_frame,
            gray_mean          = gray_mean,
            gray_std           = gray_std,
            gray_p99           = stats.gray_p99,
            hotspot_mean       = stats.hotspot_mean,
            saturated_fraction = stats.saturated_fraction,
            frame_count        = n_frames,
            frames_used        = n_kept,
            outliers_rejected  = n_outliers,
        )