"""
Plausibility checks for transmission-based layer thickness measurements.

This module implements three hard-error checks:

    1.  Light saturation on the reference capture (GW ≥ 254)
    2.  Signal-too-weak on the sample capture (GW < 10)
    3.  Samples swapped (GW_sample > GW_reference, i.e. transmission ≥ 100 %)

In addition it issues non-blocking WARNING-level results when the gray
values are approaching those thresholds, so the user gets early feedback
before a measurement becomes unusable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PlausibilitySeverity(Enum):
    """Severity of a plausibility check result."""
    OK      = "ok"        # No issues detected.
    WARNING = "warning"   # Non-blocking: measurement may proceed, but
                          # the user should be informed.
    ERROR   = "error"     # Blocking: calculation must be aborted to
                          # avoid producing garbage values.


class PlausibilityCode(Enum):
    """
    Machine-readable identifier for the specific check that triggered.
    Useful for localisation, analytics, and unit tests without matching
    on free-form strings.
    """
    OK                    = "ok"
    SATURATION_REFERENCE  = "saturation_reference"
    SATURATION_SAMPLE     = "saturation_sample"
    SIGNAL_TOO_WEAK       = "signal_too_weak"
    SAMPLES_SWAPPED       = "samples_swapped"


@dataclass(frozen=True)
class PlausibilityResult:
    """
    Immutable result of a plausibility check.

    Attributes
    ----------
    ok       : True only for OK and WARNING severities.  Callers that
               just want to know "can I continue?" should use this.
    severity : One of PlausibilitySeverity.
    code     : One of PlausibilityCode.
    title    : Short human-readable title (suitable for InfoBar / dialog).
    message  : Actionable description — tells the user what to do about it.
    """
    ok:       bool
    severity: PlausibilitySeverity
    code:     PlausibilityCode
    title:    str
    message:  str

    # ------------------------------------------------------------------
    # Convenience factories
    # ------------------------------------------------------------------
    @classmethod
    def passed(cls) -> "PlausibilityResult":
        """Returns the canonical 'all good' result."""
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
    Runs plausibility checks on gray values obtained from the camera.

    All thresholds refer to 8-bit grayscale intensities (0 - 255) as
    produced by the BGR→gray conversion in the camera / calculation
    services.

    Thresholds
    ----------
    SATURATION_ERROR_THRESHOLD    :  GW ≥ this  →  ERROR on reference
    SATURATION_WARNING_THRESHOLD  :  GW ≥ this  →  WARNING on reference
    SIGNAL_ERROR_THRESHOLD        :  GW <  this →  ERROR on sample
    SIGNAL_WARNING_THRESHOLD      :  GW <  this →  WARNING on sample

    The defaults are those given for the IDS UI-1240LE-C-HQ. Override 
    them by constructing the service with different values if you change 
    the hardware.
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
    ):
        """
        All thresholds are optional; when omitted the class-level defaults
        are used.  Passing custom values is useful for testing or for
        adapting the service to a different sensor.
        """
        self.sat_err  = saturation_error_threshold   if saturation_error_threshold   is not None else self.SATURATION_ERROR_THRESHOLD
        self.sat_warn = saturation_warning_threshold if saturation_warning_threshold is not None else self.SATURATION_WARNING_THRESHOLD
        self.sig_err  = signal_error_threshold       if signal_error_threshold       is not None else self.SIGNAL_ERROR_THRESHOLD
        self.sig_warn = signal_warning_threshold     if signal_warning_threshold     is not None else self.SIGNAL_WARNING_THRESHOLD

        # Sanity check: warning thresholds must be strictly inside the
        # error thresholds, otherwise the WARNING band is empty.
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
    # Individual checks (use these for immediate post-capture feedback)
    # ------------------------------------------------------------------

    def check_reference(self, gray_mean: float) -> PlausibilityResult:
        """
        Validates the reference capture (substrate without metal layer).

        Called by the controller immediately after the reference image
        has been captured, so the user knows *now* whether the exposure
        needs to be reduced — not 30 seconds later when the calculation
        fails.
        """
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
        """
        Validates the sample capture (substrate with metal layer).

        Runs, in order:
          1. Signal-too-weak check (implies sample is too thick or beam blocked).
          2. Samples-swapped check (only if ref_gray_mean was provided).
          3. Low-signal WARNING (elevated uncertainty).

        Pass ref_gray_mean whenever it is known; it enables the third
        hard-error check from BA1.
        """
        # 1. Signal too weak — below the noise floor of the CMOS sensor
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
                    f"range (typically > 60–70 nm for Cu at 635 nm), the laser "
                    f"is off, or the beam path is blocked."
                ),
            )

        # 2. Samples swapped — transmission ≥ 100 % is physically impossible
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

        # 3. Low-signal WARNING — result will have elevated uncertainty
        if gray_mean < self.sig_warn:
            return PlausibilityResult(
                ok       = True,
                severity = PlausibilitySeverity.WARNING,
                code     = PlausibilityCode.SIGNAL_TOO_WEAK,
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
        Final gate run by CalculationService immediately before the
        Beer-Lambert computation.

        Strategy: return the most severe finding across both captures.
        ERROR always wins; among multiple WARNINGs the reference warning
        is reported first (its root cause must be fixed first anyway).
        """
        ref_result = self.check_reference(ref_gray_mean)
        if ref_result.is_error:
            return ref_result

        sample_result = self.check_sample(sample_gray_mean, ref_gray_mean)
        if sample_result.is_error:
            return sample_result

        # No errors — surface the most actionable warning, if any.
        # Reference warnings are surfaced first because saturation on the
        # reference affects every subsequent measurement made with the
        # same exposure settings.
        if ref_result.is_warning:
            return ref_result
        if sample_result.is_warning:
            return sample_result

        return PlausibilityResult.passed()