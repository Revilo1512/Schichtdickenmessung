"""
Plausibility checks for transmission-based layer thickness measurements.

Three hard-error gates run before Beer-Lambert calculation:

  1. Saturation (open box)   — saturated_fraction >= threshold on
     either image indicates over-exposure or an open enclosure.
  2. Signal too weak (dark)  — gray_mean below the noise floor on
     either image means the sample is too thick for the measurable
     range, or the laser is off / blocked.
  3. Samples swapped         — sample gray_mean > reference gray_mean
     implies transmission >= 100 %, which is physically impossible.

All checks operate on the full-image gray mean (ITU-R 601 luminance
averaged over every pixel), matching the value used for the
Beer-Lambert calculation itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from layer_thickness_app.config.config import AppConfig

if TYPE_CHECKING:
    from layer_thickness_app.services.material_profiles import MaterialProfile
    from layer_thickness_app.services.camera_service    import FrameCaptureResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PlausibilitySeverity(Enum):
    OK    = "ok"
    ERROR = "error"


class PlausibilityCode(Enum):
    OK               = "ok"
    SATURATION       = "saturation"
    SIGNAL_TOO_WEAK  = "signal_too_weak"
    SAMPLES_SWAPPED  = "samples_swapped"


@dataclass(frozen=True)
class PlausibilityResult:
    ok:       bool
    severity: PlausibilitySeverity
    code:     PlausibilityCode
    title:    str
    message:  str

    @classmethod
    def passed(cls) -> "PlausibilityResult":
        return cls(
            ok       = True,
            severity = PlausibilitySeverity.OK,
            code     = PlausibilityCode.OK,
            title    = "OK",
            message  = "",
        )

    @property
    def is_error(self) -> bool:
        return self.severity is PlausibilitySeverity.ERROR

    @property
    def is_warning(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PlausibilityService:
    """Full-image plausibility checks: saturation, dark, swapped."""

    def __init__(
        self,
        sat_frac_error_threshold:  float | None = None,
        gray_mean_min_threshold:   float | None = None,
        profile:                   "MaterialProfile | None" = None,
    ):
        self.sat_frac_err = (
            sat_frac_error_threshold
            if sat_frac_error_threshold is not None
            else AppConfig.PLAUSIBILITY_SAT_FRAC_ERR
        )
        self.gray_mean_min = (
            gray_mean_min_threshold
            if gray_mean_min_threshold is not None
            else AppConfig.PLAUSIBILITY_GRAY_MEAN_MIN
        )

        if profile is not None:
            self.sat_frac_err  = profile.saturation_frac_err
            self.gray_mean_min = profile.gray_mean_min
            logger.info(
                "Plausibility profile applied: %s "
                "(sat_frac_err=%.4f, gray_mean_min=%.2f)",
                profile.label, self.sat_frac_err, self.gray_mean_min,
            )

    # ------------------------------------------------------------------
    # Capture-level entry points
    # ------------------------------------------------------------------

    def check_reference_capture(
        self, capture: "FrameCaptureResult",
    ) -> PlausibilityResult:
        return self._check_reference(
            saturated_fraction = capture.saturated_fraction,
            gray_mean          = capture.gray_mean,
        )

    def check_sample_capture(
        self,
        capture:           "FrameCaptureResult",
        reference_capture: "FrameCaptureResult | None" = None,
    ) -> PlausibilityResult:
        ref_gray = (
            reference_capture.gray_mean
            if reference_capture is not None else None
        )
        return self._check_sample(
            saturated_fraction = capture.saturated_fraction,
            gray_mean          = capture.gray_mean,
            ref_gray_mean      = ref_gray,
        )

    def check_pair_captures(
        self,
        reference_capture: "FrameCaptureResult",
        sample_capture:    "FrameCaptureResult",
    ) -> PlausibilityResult:
        """Combined gate run before Beer-Lambert. First error wins."""
        ref_result = self.check_reference_capture(reference_capture)
        if ref_result.is_error:
            return ref_result

        sample_result = self.check_sample_capture(sample_capture, reference_capture)
        if sample_result.is_error:
            return sample_result

        return PlausibilityResult.passed()

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _check_reference(
        self,
        saturated_fraction: float,
        gray_mean:          float,
    ) -> PlausibilityResult:
        # 1. Saturation (open box / over-exposure)
        if saturated_fraction >= self.sat_frac_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SATURATION,
                title    = "Image Oversaturated (Open Box)",
                message  = (
                    f"{saturated_fraction * 100.0:.2f} % of reference pixels "
                    f"are clipped (>= 254). The image is oversaturated — "
                    f"check that the enclosure is closed, reduce exposure "
                    f"time, or insert a neutral-density filter."
                ),
            )

        # 2. Signal too weak (laser off / blocked)
        if gray_mean < self.gray_mean_min:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SIGNAL_TOO_WEAK,
                title    = "Reference Too Dark",
                message  = (
                    f"Reference gray mean ({gray_mean:.2f}) is below the "
                    f"noise floor ({self.gray_mean_min:.1f}). Check that the "
                    f"laser is on and the beam path is clear."
                ),
            )

        return PlausibilityResult.passed()

    def _check_sample(
        self,
        saturated_fraction: float,
        gray_mean:          float,
        ref_gray_mean:      float | None = None,
    ) -> PlausibilityResult:
        # 1. Saturation on sample (physically impossible unless swapped)
        if saturated_fraction >= self.sat_frac_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SATURATION,
                title    = "Sample Image Oversaturated",
                message  = (
                    f"{saturated_fraction * 100.0:.2f} % of sample pixels "
                    f"are clipped. A saturated sample image implies the "
                    f"sample is missing or swapped with the reference."
                ),
            )

        # 2. Signal too weak (sample too thick or laser off)
        if gray_mean < self.gray_mean_min:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SIGNAL_TOO_WEAK,
                title    = "Sample Too Dark",
                message  = (
                    f"Sample gray mean ({gray_mean:.2f}) is below the noise "
                    f"floor ({self.gray_mean_min:.1f}). The sample thickness "
                    f"likely exceeds the measurable range for this material, "
                    f"or the laser is off."
                ),
            )

        # 3. Swapped: sample brighter than reference
        if ref_gray_mean is not None and gray_mean > ref_gray_mean:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SAMPLES_SWAPPED,
                title    = "Reference and Sample Swapped",
                message  = (
                    f"Sample gray mean ({gray_mean:.2f}) is higher than "
                    f"reference gray mean ({ref_gray_mean:.2f}). This would "
                    f"mean transmission >= 100 %, which is physically "
                    f"impossible. Reference and sample were likely swapped."
                ),
            )

        return PlausibilityResult.passed()