from __future__ import annotations

import math
import logging
from typing import Any, TYPE_CHECKING

import numpy as np
import refractiveindex2 as ri

from layer_thickness_app.services.plausibility_service import (
    PlausibilityService,
    PlausibilityResult,
)

if TYPE_CHECKING:
    from layer_thickness_app.services.camera_service import FrameCaptureResult

logger = logging.getLogger(__name__)


class CalculationService:
    """
    Converts camera captures into a layer thickness value via the
    Beer-Lambert law, with integrated plausibility checks.

    Entry point
    -----------
    calculate_thickness_from_captures() — accepts two FrameCaptureResult
    objects whose gray_mean values have already been computed by the
    multi-frame averaging logic. Runs the plausibility gate FIRST and
    aborts early on hard errors. Returns
    (thickness_nm | None, error_msg | None, capture_stats: dict).
    """

    # Linearisation constants (sRGB gamma approximation).
    # Do not change without re-running the full calibration.
    LINEARIZATION_OFFSET_1 = 0.055
    LINEARIZATION_OFFSET_2 = 1.005
    LINEARIZATION_EXPONENT = 2.4

    def __init__(self, plausibility_service: PlausibilityService | None = None):
        """
        The plausibility service is dependency-injected so the controller
        can swap in a profile-bound instance for one calculation and keep
        its own long-lived default service for post-capture feedback.
        """
        self.plausibility: PlausibilityService = (
            plausibility_service if plausibility_service is not None
            else PlausibilityService()
        )

    # ==================================================================
    # Main path
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

        Order of operations
        -------------------
        1. Frame-count consistency check (reference and sample must have
           been captured with the same n_frames, otherwise their noise
           characteristics differ and comparing them is invalid).
        2. Build capture_stats (always populated, even on early exit).
        3. Plausibility gate — hard errors abort here.
        4. Material lookup (k).
        5. Absorption coefficient (alpha).
        6. Linearisation.
        7. Beer-Lambert -> thickness in nm.
        """
        # -- 1. Frame-count consistency --
        if ref_result.frame_count != mat_result.frame_count:
            error_msg = (
                f"Frame count mismatch: reference={ref_result.frame_count}, "
                f"sample={mat_result.frame_count} — capture both with the "
                f"same frame count."
            )
            logger.error(error_msg)
            return None, error_msg, {}

        material_path = f"{shelf}/{book}/{page}"
        logger.info(
            "calculate_thickness_from_captures | material=%s | λ=%.4f µm | "
            "ref_gray=%.3f sat=%.4f n=%d | "
            "mat_gray=%.3f sat=%.4f n=%d",
            material_path, wavelength_um,
            ref_result.gray_mean,
            ref_result.saturated_fraction, ref_result.frames_used,
            mat_result.gray_mean,
            mat_result.saturated_fraction, mat_result.frames_used,
        )

        # -- 2. Capture stats (returned even on early failure) --
        frame_count = ref_result.frame_count
        capture_stats: dict[str, Any] = {
            "MeanGrayRef":          round(ref_result.gray_mean, 4),
            "MeanGraySample":       round(mat_result.gray_mean, 4),
            "StdGrayRef":           round(ref_result.gray_std,  4),
            "StdGraySample":        round(mat_result.gray_std,  4),
            "SaturatedFractionRef": round(ref_result.saturated_fraction, 6),
            "SaturatedFractionSample": round(mat_result.saturated_fraction, 6),
            "FrameCountRef":        ref_result.frame_count,
            "FrameCountSample":     mat_result.frame_count,
            "Mode":                 "multi" if frame_count > 1 else "single",
        }

        # -- 3. Plausibility gate --
        plaus = self.plausibility.check_pair_captures(
            reference_capture = ref_result,
            sample_capture    = mat_result,
        )
        self._attach_plausibility(capture_stats, plaus)

        if plaus.is_error:
            logger.warning(
                "Plausibility check failed: %s — %s",
                plaus.code.value, plaus.title,
            )
            return None, f"{plaus.title}: {plaus.message}", capture_stats

        # -- 4. Extinction coefficient k --
        k, k_error = self._get_extinction_coefficient(shelf, book, page, wavelength_um)
        if k_error:
            return None, k_error, capture_stats

        # -- 5. Absorption coefficient alpha --
        try:
            alpha_cm = self.calculate_alpha(k, wavelength_um)
            logger.info("α = %.4e cm⁻¹", alpha_cm)
        except ValueError as e:
            return None, f"Math Error: {e}", capture_stats

        # -- 6. Linearise the pre-computed gray means --
        lin_ref = self.linearize_mean_pixel_value(ref_result.gray_mean)
        lin_mat = self.linearize_mean_pixel_value(mat_result.gray_mean)

        # -- 7. Beer-Lambert -> thickness --
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
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _attach_plausibility(
        stats: dict[str, Any], result: PlausibilityResult,
    ) -> None:
        """Write the plausibility outcome into transient stats keys."""
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

    def linearize_mean_pixel_value(self, gw: float) -> float:
        """
        sRGB gamma linearisation of a 0-255 gray value:
            gw_norm_lin = ((gw / 255 + O1) / O2) ** E
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
        Beer-Lambert:  I = I0 * e^(-alpha*d)   ->   d = -ln(I / I0) / alpha
        Returns thickness in nm, or None if inputs are unphysical.
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
        """Absorption coefficient alpha [cm^-1]:  alpha = 4*pi*k / lambda"""
        if lambda_um <= 0:
            raise ValueError("Wavelength must be > 0.")
        lambda_cm = lambda_um * 1e-4
        return (4.0 * math.pi * k) / lambda_cm