"""
Plausibility checks for transmission-based layer thickness measurements.

Hard-error checks
-----------------
1.  Light saturation on the reference capture (GW ≥ sat_err)
2.  Signal-too-weak on the sample capture (GW < sig_err)
3.  Samples swapped (GW_sample > GW_reference, i.e. transmission ≥ 100 %)

Non-blocking WARNINGs are issued before those thresholds are reached so
the user can adjust exposure before producing an unusable measurement.

Thresholds can be supplied per material via a MaterialProfile; absent a
profile the class-level defaults (tuned for an IDS UI-1240LE-C-HQ) are
used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from layer_thickness_app.services.material_profiles import MaterialProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PlausibilitySeverity(Enum):
    OK      = "ok"
    WARNING = "warning"
    ERROR   = "error"


class PlausibilityCode(Enum):
    """Machine-readable identifier for the specific check that triggered."""
    OK                    = "ok"
    SATURATION_REFERENCE  = "saturation_reference"
    SATURATION_SAMPLE     = "saturation_sample"
    SIGNAL_TOO_WEAK       = "signal_too_weak"
    SIGNAL_LOW_WARN       = "signal_low_warn"
    SAMPLES_SWAPPED       = "samples_swapped"


@dataclass(frozen=True)
class PlausibilityResult:
    """Immutable result of a plausibility check."""
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
    """
    Runs plausibility checks on gray values (0-255 uint8) from the camera.

    Thresholds
    ----------
    SATURATION_ERROR_THRESHOLD    :  GW ≥ this  →  ERROR on reference
    SATURATION_WARNING_THRESHOLD  :  GW ≥ this  →  WARNING on reference
    SIGNAL_ERROR_THRESHOLD        :  GW <  this →  ERROR on sample
    SIGNAL_WARNING_THRESHOLD      :  GW <  this →  WARNING on sample

    When a MaterialProfile is supplied at construction, its saturation_warn
    and signal_warn values override the class-level defaults for the two
    warning bands. The error thresholds remain fixed because they describe
    hardware limits (sensor saturation / noise floor), not material-specific
    behaviour.
    """

    # --- Class-level defaults ------------------------
    SATURATION_ERROR_THRESHOLD:   float = 254.0
    SATURATION_WARNING_THRESHOLD: float = 240.0
    SIGNAL_ERROR_THRESHOLD:       float = 10.0
    SIGNAL_WARNING_THRESHOLD:     float = 20.0

    def __init__(
        self,
        saturation_error_threshold:   float | None = None,
        saturation_warning_threshold: float | None = None,
        signal_error_threshold:       float | None = None,
        signal_warning_threshold:     float | None = None,
        profile:                      "MaterialProfile | None" = None,
    ):
        self.sat_err  = saturation_error_threshold   if saturation_error_threshold   is not None else self.SATURATION_ERROR_THRESHOLD
        self.sat_warn = saturation_warning_threshold if saturation_warning_threshold is not None else self.SATURATION_WARNING_THRESHOLD
        self.sig_err  = signal_error_threshold       if signal_error_threshold       is not None else self.SIGNAL_ERROR_THRESHOLD
        self.sig_warn = signal_warning_threshold     if signal_warning_threshold     is not None else self.SIGNAL_WARNING_THRESHOLD

        if profile is not None:
            # Profile-supplied warning bands override constructor / defaults.
            self.sat_warn = profile.saturation_warn
            self.sig_warn = profile.signal_warn
            # Profile may also tighten the signal error threshold.
            self.sig_err  = profile.signal_err
            logger.info(
                "Plausibility profile applied: %s (sat_warn=%.1f, sig_warn=%.1f, sig_err=%.1f)",
                profile.label, self.sat_warn, self.sig_warn, self.sig_err,
            )

        # Sanity check
        if self.sat_warn > self.sat_err:
            logger.warning(
                "Saturation warning threshold (%.1f) > error threshold (%.1f). "
                "The warning band will never trigger.", self.sat_warn, self.sat_err,
            )
        if self.sig_warn < self.sig_err:
            logger.warning(
                "Signal warning threshold (%.1f) < error threshold (%.1f). "
                "The warning band will never trigger.", self.sig_warn, self.sig_err,
            )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_reference(self, gray_mean: float) -> PlausibilityResult:
        """Validates the reference capture (substrate without layer)."""
        if gray_mean >= self.sat_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SATURATION_REFERENCE,
                title    = "Light Saturation Detected",
                message  = (
                    f"Reference gray value ({gray_mean:.1f}) is at or above the "
                    f"saturation limit ({self.sat_err:.0f}). Pixels are clipped "
                    f"and the measurement will be invalid.\n\n"
                    f"Please reduce the exposure time or add a neutral-density "
                    f"filter to the beam path."
                ),
            )

        if gray_mean >= self.sat_warn:
            return PlausibilityResult(
                ok       = True,
                severity = PlausibilitySeverity.WARNING,
                code     = PlausibilityCode.SATURATION_REFERENCE,
                title    = "Reference Near Saturation",
                message  = (
                    f"Reference gray value ({gray_mean:.1f}) is close to "
                    f"saturation ({self.sat_err:.0f}). Consider reducing the "
                    f"exposure slightly to preserve headroom for lighter samples."
                ),
            )

        return PlausibilityResult.passed()

    def check_sample(
        self,
        gray_mean:     float,
        ref_gray_mean: float | None = None,
    ) -> PlausibilityResult:
        """Validates the sample capture (substrate with layer)."""
        if gray_mean < self.sig_err:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SIGNAL_TOO_WEAK,
                title    = "Sample Signal Too Weak",
                message  = (
                    f"Sample gray value ({gray_mean:.1f}) is below the sensor "
                    f"noise floor ({self.sig_err:.0f}). Any calculated thickness "
                    f"would be dominated by noise.\n\n"
                    f"Likely causes: sample thickness exceeds the measurable "
                    f"range for this material, the laser is off, or the beam "
                    f"path is blocked."
                ),
            )

        if ref_gray_mean is not None and gray_mean > ref_gray_mean:
            return PlausibilityResult(
                ok       = False,
                severity = PlausibilitySeverity.ERROR,
                code     = PlausibilityCode.SAMPLES_SWAPPED,
                title    = "Samples Possibly Swapped",
                message  = (
                    f"Sample gray value ({gray_mean:.1f}) is brighter than the "
                    f"reference ({ref_gray_mean:.1f}). This would imply "
                    f"transmission ≥ 100 %, which is physically impossible.\n\n"
                    f"Did you swap the reference and sample captures, or was "
                    f"the reference taken with a sample still in the beam path?"
                ),
            )

        if gray_mean < self.sig_warn:
            return PlausibilityResult(
                ok       = True,
                severity = PlausibilitySeverity.WARNING,
                code     = PlausibilityCode.SIGNAL_LOW_WARN,
                title    = "Low Sample Signal",
                message  = (
                    f"Sample gray value ({gray_mean:.1f}) is low "
                    f"(< {self.sig_warn:.0f}). The calculated thickness will "
                    f"have increased uncertainty — enabling multi-frame "
                    f"averaging is recommended."
                ),
            )

        return PlausibilityResult.passed()

    # ------------------------------------------------------------------
    # Combined pre-calculation gate
    # ------------------------------------------------------------------

    def check_pair(
        self,
        ref_gray_mean:    float,
        sample_gray_mean: float,
    ) -> PlausibilityResult:
        """
        Final gate run before Beer-Lambert computation.
        Returns the most severe finding across both captures; reference
        issues are reported first because their root cause must be fixed
        first anyway.
        """
        ref_result = self.check_reference(ref_gray_mean)
        if ref_result.is_error:
            return ref_result

        sample_result = self.check_sample(sample_gray_mean, ref_gray_mean)
        if sample_result.is_error:
            return sample_result

        if ref_result.is_warning:
            return ref_result
        if sample_result.is_warning:
            return sample_result

        return PlausibilityResult.passed()