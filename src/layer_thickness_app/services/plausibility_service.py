"""
Plausibility checks for transmission-based layer thickness measurements.

The transmission setup produces a small bright spot in an otherwise
dark frame. Both saturation and signal-strength checks therefore use
spot statistics rather than the global gray mean:

  * Saturation is detected by the fraction of pixels at or above 254
    (clipping in the spot, even when most of the frame is dark).
  * Signal strength is the mean over the top 1 % of pixels (the spot
    itself), which stays meaningful for thick layers where the spot
    shrinks and drags the global mean below the noise floor.

Hard errors:
    1. Reference saturation       (saturated_fraction >= sat_frac_err)
    2. Sample signal too weak     (hotspot_mean < hotspot_err)
    3. Samples swapped            (hotspot_sample > hotspot_reference)

Non-blocking warnings are issued before the hard thresholds are reached
so the operator can adjust exposure before producing an unusable
measurement. A MaterialProfile may override the warning bands and the
sample signal-error threshold; the saturation error threshold remains
fixed because it describes a hardware ceiling.
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
    OK      = "ok"
    WARNING = "warning"
    ERROR   = "error"


class PlausibilityCode(Enum):
    OK                    = "ok"
    SATURATION_REFERENCE  = "saturation_reference"
    SATURATION_SAMPLE     = "saturation_sample"
    SIGNAL_TOO_WEAK       = "signal_too_weak"
    SIGNAL_LOW_WARN       = "signal_low_warn"
    SAMPLES_SWAPPED       = "samples_swapped"


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
        return self.severity is PlausibilitySeverity.WARNING


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PlausibilityService:
    """Runs spot-aware plausibility checks on a captured frame."""

    def __init__(
        self,
        sat_frac_error_threshold:    float | None = None,
        sat_frac_warning_threshold:  float | None = None,
        hotspot_error_threshold:     float | None = None,
        hotspot_warning_threshold:   float | None = None,
        profile:                     "MaterialProfile | None" = None,
    ):
        self.sat_frac_err = (
            sat_frac_error_threshold
            if sat_frac_error_threshold is not None
            else AppConfig.PLAUSIBILITY_SAT_FRAC_ERR
        )
        self.sat_frac_warn = (
            sat_frac_warning_threshold
            if sat_frac_warning_threshold is not None
            else AppConfig.PLAUSIBILITY_SAT_FRAC_WARN
        )
        self.hotspot_err = (
            hotspot_error_threshold
            if hotspot_error_threshold is not None
            else AppConfig.PLAUSIBILITY_HOTSPOT_ERR
        )
        self.hotspot_warn = (
            hotspot_warning_threshold
            if hotspot_warning_threshold is not None
            else AppConfig.PLAUSIBILITY_HOTSPOT_WARN
        )

        if profile is not None:
            self.sat_frac_warn = profile.saturation_frac_warn
            self.sat_frac_err  = profile.saturation_frac_err
            self.hotspot_warn  = profile.hotspot_warn
            self.hotspot_err   = profile.hotspot_err
            logger.info(
                "Plausibility profile applied: %s "
                "(sat_frac_warn=%.4f, sat_frac_err=%.4f, "
                "hotspot_warn=%.1f, hotspot_err=%.1f)",
                profile.label, self.sat_frac_warn, self.sat_frac_err,
                self.hotspot_warn, self.hotspot_err,
            )

        if self.sat_frac_warn > self.sat_frac_err:
            logger.warning(
                "Saturation warning fraction (%.4f) > error fraction (%.4f); "
                "warning band disabled.",
                self.sat_frac_warn, self.sat_frac_err,
            )
        if self.hotspot_warn < self.hotspot_err:
            logger.warning(
                "Hotspot warning (%.1f) < error (%.1f); warning band disabled.",
                self.hotspot_warn, self.hotspot_err,
            )

    # ------------------------------------------------------------------
    # Capture-level entry points (preferred)
    # ------------------------------------------------------------------

    def check_reference_capture(
        self, capture: "FrameCaptureResult",
    ) -> PlausibilityResult:
        return self._check_reference(
            saturated_fraction = capture.saturated_fraction,
            hotspot_mean       = capture.hotspot_mean,
        )

    def check_sample_capture(
        self,
        capture:           "FrameCaptureResult",
        reference_capture: "FrameCaptureResult | None" = None,
    ) -> PlausibilityResult:
        ref_hotspot = (
            reference_capture.hotspot_mean
            if reference_capture is not None else None
        )
        return self._check_sample(
            saturated_fraction = capture.saturated_fraction,
            hotspot_mean       = capture.hotspot_mean,
            ref_hotspot_mean   = ref_hotspot,
        )

    def check_pair_captures(
        self,
        reference_capture: "FrameCaptureResult",
        sample_capture:    "FrameCaptureResult",
    ) -> PlausibilityResult:
        """Combined gate run before Beer-Lambert. Most severe finding wins."""
        ref_result = self.check_reference_capture(reference_capture)
        if ref_result.is_error:
            return ref_result

        sample_result = self.check_sample_capture(sample_capture, reference_capture)
        if sample_result.is_error:
            return sample_result

        if ref_result.is_warning:
            return ref_result
        if sample_result.is_warning:
            return sample_result

        return PlausibilityResult.passed()

    # ------------------------------------------------------------------
    # Scalar entry points (used by tests and any caller that doesn't
    # have a full FrameCaptureResult on hand).
    # ------------------------------------------------------------------

    def _check_reference(
        self,
        saturated_fraction: float,
        hotspot_mean:       float,
    ) -> PlausibilityResult:
        if saturated_fraction >= self.sat_frac_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SATURATION_REFERENCE,
                title    = "Light Saturation Detected",
                message  = (
                    f"{saturated_fraction * 100.0:.2f} % of reference pixels "
                    f"are clipped (>= 254), which exceeds the "
                    f"{self.sat_frac_err * 100.0:.2f} % limit. The laser "
                    f"spot is over-exposed and the measurement will be "
                    f"invalid.\n\n"
                    f"Reduce the exposure time or insert a neutral-density "
                    f"filter into the beam path."
                ),
            )
        if saturated_fraction >= self.sat_frac_warn:
            return PlausibilityResult(
                ok       = True,
                severity = PlausibilitySeverity.WARNING,
                code     = PlausibilityCode.SATURATION_REFERENCE,
                title    = "Reference Near Saturation",
                message  = (
                    f"{saturated_fraction * 100.0:.2f} % of pixels are at "
                    f"the saturation ceiling. The spot is close to clipping; "
                    f"reduce the exposure slightly to preserve headroom."
                ),
            )

        # Even a non-clipped reference can be too dim to be useful.
        if hotspot_mean < self.hotspot_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SIGNAL_TOO_WEAK,
                title    = "Reference Spot Too Dim",
                message  = (
                    f"Reference hotspot intensity ({hotspot_mean:.1f}) is "
                    f"below the noise floor ({self.hotspot_err:.0f}). "
                    f"Increase the exposure time or check that the laser is "
                    f"on and the beam path is clear."
                ),
            )
        return PlausibilityResult.passed()

    def _check_sample(
        self,
        saturated_fraction: float,
        hotspot_mean:       float,
        ref_hotspot_mean:   float | None = None,
    ) -> PlausibilityResult:
        # A clipped sample frame is unphysical (transmission > 1) and is
        # almost always a swap or a misaligned reference.
        if saturated_fraction >= self.sat_frac_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SATURATION_SAMPLE,
                title    = "Sample Saturation Detected",
                message  = (
                    f"{saturated_fraction * 100.0:.2f} % of sample pixels "
                    f"are clipped. A sample frame at saturation implies "
                    f"the sample is missing or swapped with the reference."
                ),
            )

        if hotspot_mean < self.hotspot_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SIGNAL_TOO_WEAK,
                title    = "Sample Signal Too Weak",
                message  = (
                    f"Sample hotspot intensity ({hotspot_mean:.1f}) is "
                    f"below the noise floor ({self.hotspot_err:.0f}). Any "
                    f"calculated thickness would be dominated by noise.\n\n"
                    f"Likely causes: sample thickness exceeds the measurable "
                    f"range for this material, the laser is off, or the beam "
                    f"path is blocked."
                ),
            )

        if ref_hotspot_mean is not None and hotspot_mean > ref_hotspot_mean:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SAMPLES_SWAPPED,
                title    = "Samples Possibly Swapped",
                message  = (
                    f"Sample hotspot ({hotspot_mean:.1f}) is brighter than "
                    f"the reference hotspot ({ref_hotspot_mean:.1f}). This "
                    f"implies transmission >= 100 %, which is physically "
                    f"impossible.\n\n"
                    f"Did you swap the reference and sample captures, or was "
                    f"the reference taken with a sample still in the beam "
                    f"path?"
                ),
            )

        if hotspot_mean < self.hotspot_warn:
            return PlausibilityResult(
                ok       = True,
                severity = PlausibilitySeverity.WARNING,
                code     = PlausibilityCode.SIGNAL_LOW_WARN,
                title    = "Low Sample Signal",
                message  = (
                    f"Sample hotspot intensity ({hotspot_mean:.1f}) is low "
                    f"(< {self.hotspot_warn:.0f}). The calculated thickness "
                    f"will have increased uncertainty; multi-frame averaging "
                    f"is recommended."
                ),
            )

        return PlausibilityResult.passed()