from __future__ import annotations

import math
import logging
import cv2
import numpy as np
import refractiveindex2 as ri
from typing import Any, TYPE_CHECKING

from layer_thickness_app.services.plausibility_service import (
    PlausibilityService,
    PlausibilityResult,
)

if TYPE_CHECKING:
    # Imported only for type-checker — avoids any circular import risk at
    # runtime while still giving full autocomplete / mypy support.
    from layer_thickness_app.services.camera_service import FrameCaptureResult

logger = logging.getLogger(__name__)


class CalculationService:
    """
    Converts camera captures into a layer thickness value via the
    Beer-Lambert law, with integrated plausibility checks.

    Two public entry points
    -----------------------
    calculate_thickness_from_captures()   – NEW main path (Step 2+).
        Accepts two FrameCaptureResult objects whose gray_mean values
        have already been computed by the multi-frame averaging logic.
        Runs the plausibility gate FIRST and aborts early on hard errors.
        Returns (thickness_nm | None, error_msg | None, capture_stats: dict).
        capture_stats contains:
          - DB-bound keys (MeanGrayRef, Mode, FrameCount, …) consumed by
            database_service.save_measurement.  Unknown keys are silently
            dropped there, so the extra plausibility keys are harmless.
          - Transient keys used by the UI:
              plausibility_ok        : bool
              plausibility_severity  : 'ok' | 'warning' | 'error'
              plausibility_code      : machine-readable code
              plausibility_title     : short title
              plausibility_message   : actionable description

    calculate_thickness()                 – ORIGINAL backward-compat path.
        Accepts raw BGR numpy arrays (as before).  Internally wraps the
        new method.  Plausibility checks still run; errors surface via
        the returned error_msg so no existing caller is silently bypassed.
        Returns the original 2-tuple: (thickness_nm | None, error_msg | None).
    """

    # ------------------------------------------------------------------
    # Linearisation constants (sRGB gamma approximation used by the
    # original Burkhardt implementation — do NOT change without re-running
    # the full calibration).
    # ------------------------------------------------------------------
    LINEARIZATION_OFFSET_1 = 0.055
    LINEARIZATION_OFFSET_2 = 1.005
    LINEARIZATION_EXPONENT = 2.4

    def __init__(self, plausibility_service: PlausibilityService | None = None):
        """
        The plausibility service is dependency-injected so callers can
        supply a pre-configured instance (e.g. with custom thresholds
        for a different sensor).  When omitted, a default instance with
        the BA1 §4.2.3 thresholds is used.
        """
        self.plausibility: PlausibilityService = (
            plausibility_service if plausibility_service is not None
            else PlausibilityService()
        )

    # ==================================================================
    # NEW MAIN PATH  (Step 2+)
    # ==================================================================

    def calculate_thickness_from_captures(
        self,
        ref_result:    "FrameCaptureResult",
        mat_result:    "FrameCaptureResult",
        shelf:         str,
        book:          str,
        page:          str,
        wavelength_um: float,
    ) -> tuple[float | None, str | None, dict[str, Any]]:
        """
        Full calculation pipeline operating on FrameCaptureResult objects.

        Execution order
        ---------------
        1.  Build capture_stats (always populated, even on early exit).
        2.  Plausibility gate — hard errors abort here with a clear
            user-facing message.
        3.  Material lookup (k).
        4.  Absorption coefficient (α).
        5.  Linearisation.
        6.  Beer-Lambert → thickness in nm.
        """
        material_path = f"{shelf}/{book}/{page}"
        logger.info(
            "calculate_thickness_from_captures | material=%s | λ=%.4f µm | "
            "ref_gray=%.3f (σ=%.3f, n=%d) | mat_gray=%.3f (σ=%.3f, n=%d)",
            material_path, wavelength_um,
            ref_result.gray_mean, ref_result.gray_std, ref_result.frames_used,
            mat_result.gray_mean, mat_result.gray_std, mat_result.frames_used,
        )

        # ── 1. Capture stats (returned even on early failure) ─────────
        frame_count = max(ref_result.frame_count, mat_result.frame_count)
        capture_stats: dict[str, Any] = {
            # DB-bound keys — consumed by save_measurement
            "MeanGrayRef":    round(ref_result.gray_mean, 4),
            "MeanGraySample": round(mat_result.gray_mean, 4),
            "StdGrayRef":     round(ref_result.gray_std,  4),
            "StdGraySample":  round(mat_result.gray_std,  4),
            "FrameCount":     frame_count,
            "Mode":           "multi" if frame_count > 1 else "single",
        }

        # ── 2. Plausibility gate ──────────────────────────────────────
        plaus = self.plausibility.check_pair(
            ref_gray_mean    = ref_result.gray_mean,
            sample_gray_mean = mat_result.gray_mean,
        )
        self._attach_plausibility(capture_stats, plaus)

        if plaus.is_error:
            logger.warning(
                "Plausibility check failed: %s — %s",
                plaus.code.value, plaus.title,
            )
            return None, f"{plaus.title}: {plaus.message}", capture_stats

        if plaus.is_warning:
            logger.info(
                "Plausibility warning (non-blocking): %s — %s",
                plaus.code.value, plaus.title,
            )

        # ── 3. Extinction coefficient k ───────────────────────────────
        k, k_error = self._get_extinction_coefficient(shelf, book, page, wavelength_um)
        if k_error:
            return None, k_error, capture_stats

        # ── 4. Absorption coefficient α ───────────────────────────────
        try:
            alpha_cm = self.calculate_alpha(k, wavelength_um)
            logger.info("α = %.4e cm⁻¹", alpha_cm)
        except ValueError as e:
            return None, f"Math Error: {e}", capture_stats

        # ── 5. Linearise the pre-computed gray means ──────────────────
        lin_ref = self.linearize_mean_pixel_value(ref_result.gray_mean)
        lin_mat = self.linearize_mean_pixel_value(mat_result.gray_mean)

        # ── 6. Beer-Lambert → thickness ───────────────────────────────
        thickness_nm = self.calculate_thickness_from_intensity(
            intensity_transmitted = lin_mat,
            intensity_initial     = lin_ref,
            alpha                 = alpha_cm,
        )

        if thickness_nm is None:
            return (
                None,
                "Calculation Error: Invalid intensity values "
                "(check image brightness and saturation).",
                capture_stats,
            )

        logger.info("Thickness = %.4f nm", thickness_nm)
        return thickness_nm, None, capture_stats

    # ==================================================================
    # ORIGINAL BACKWARD-COMPAT PATH
    # ==================================================================

    def calculate_thickness(
        self,
        ref_image:     np.ndarray,
        mat_image:     np.ndarray,
        shelf:         str,
        book:          str,
        page:          str,
        wavelength_um: float,
    ) -> tuple[float | None, str | None]:
        """
        Original public API — accepts raw BGR frames and returns
        (thickness_nm, error_msg).  Plausibility checks still apply and
        surface via error_msg, so nothing is silently bypassed.

        This is still called by the controller until Step 4 migrates it
        to the new path.
        """
        gw_ref = self.calculate_mean_pixel_value(ref_image, "Reference")
        gw_mat = self.calculate_mean_pixel_value(mat_image, "Material")

        ref_proxy = _SingleFrameProxy(gw_ref)
        mat_proxy = _SingleFrameProxy(gw_mat)

        thickness_nm, error_msg, _ = self.calculate_thickness_from_captures(
            ref_proxy, mat_proxy, shelf, book, page, wavelength_um  # type: ignore[arg-type]
        )
        return thickness_nm, error_msg

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _attach_plausibility(
        stats: dict[str, Any], result: PlausibilityResult
    ) -> None:
        """
        Writes the plausibility outcome into the stats dict under
        transient (non-DB) keys so the controller can surface it in
        the GUI without any extra plumbing.
        """
        stats["plausibility_ok"]       = result.ok
        stats["plausibility_severity"] = result.severity.value
        stats["plausibility_code"]     = result.code.value
        stats["plausibility_title"]    = result.title
        stats["plausibility_message"]  = result.message

    def _get_extinction_coefficient(
        self,
        shelf:         str,
        book:          str,
        page:          str,
        wavelength_um: float,
    ) -> tuple[float | None, str | None]:
        """
        Fetches k from the refractiveindex2 database.
        Returns (k, None) on success or (None, error_msg) on failure.
        """
        material_path = f"{shelf}/{book}/{page}"
        try:
            material = ri.RefractiveIndexMaterial(shelf, book, page)
            k = material.get_extinction_coefficient(wavelength_um)
            logger.info("k = %.6f  (%s @ %.4f µm)", k, material_path, wavelength_um)
            return k, None
        except Exception as e:
            msg = (
                f"Material Error: could not get k for "
                f"{material_path} at {wavelength_um} µm. ({e})"
            )
            logger.error(msg)
            return None, msg

    def calculate_mean_pixel_value(
        self, image: np.ndarray, image_type: str
    ) -> float:
        """
        Converts a BGR frame to grayscale and returns the mean pixel value.
        Used by the backward-compat calculate_thickness() path and may be
        called independently for diagnostics.
        """
        gray  = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        value = float(np.mean(gray))
        logger.info("Mean gray (%s): %.4f", image_type, value)
        return value

    def linearize_mean_pixel_value(self, gw: float) -> float:
        """
        Applies the sRGB gamma linearisation to a 0–255 gray value.

        Formula:
            gw_norm      = gw / 255
            gw_norm_lin  = ((gw_norm + O1) / O2) ^ E
        where O1, O2, E are the class-level linearisation constants.
        """
        gw_norm_lin = (
            ((gw / 255.0) + self.LINEARIZATION_OFFSET_1)
            / self.LINEARIZATION_OFFSET_2
        ) ** self.LINEARIZATION_EXPONENT
        logger.debug("Linearised gray %.4f → %.6f", gw, gw_norm_lin)
        return gw_norm_lin

    def calculate_thickness_from_intensity(
        self,
        intensity_transmitted: float,
        intensity_initial:     float,
        alpha:                 float,
    ) -> float | None:
        """
        Beer-Lambert law:  I = I₀ · e^(−α·d)
        Solved for d:      d = −ln(I / I₀) / α

        Returns thickness in nm, or None if the inputs are unphysical.
        """
        if intensity_transmitted <= 0 or intensity_initial <= 0 or alpha == 0:
            logger.error(
                "Unphysical inputs: I=%.4f, I0=%.4f, α=%.4e",
                intensity_transmitted, intensity_initial, alpha,
            )
            return None
        try:
            x_cm = math.log(intensity_transmitted / intensity_initial) / (-alpha)
            x_nm = x_cm * 1e7
            logger.info("d = %.4f nm  (%.6e cm)", x_nm, x_cm)
            return x_nm
        except Exception as e:
            logger.error("Error in Beer-Lambert calculation: %s", e)
            return None

    def calculate_alpha(self, k: float, lambda_um: float) -> float:
        """
        Absorption coefficient α [cm⁻¹].

            α = 4π·k / λ

        Parameters
        ----------
        k         : extinction coefficient (dimensionless)
        lambda_um : wavelength in µm
        """
        if lambda_um <= 0:
            raise ValueError("Wavelength must be > 0.")
        lambda_cm = lambda_um * 1e-4   # µm → cm
        return (4.0 * math.pi * k) / lambda_cm


# ---------------------------------------------------------------------------
# Internal duck-type proxy used only by calculate_thickness() to avoid
# importing FrameCaptureResult at runtime while sharing the same calculation
# core.  Not part of the public API.
# ---------------------------------------------------------------------------
class _SingleFrameProxy:
    """Minimal stand-in for FrameCaptureResult with single-frame semantics."""
    __slots__ = ("gray_mean", "gray_std", "frame_count", "frames_used")

    def __init__(self, gray_mean: float):
        self.gray_mean   = gray_mean
        self.gray_std    = 0.0
        self.frame_count = 1
        self.frames_used = 1