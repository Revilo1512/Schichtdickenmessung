"""
Measurement System Analysis — Type 1 (Gage Study).

Implements the MSA Typ 1 methodology used as the 
quantitative gate for declaring the measurement
system "capable" before and after calibration.

Two capability indices are computed:

    Cg   =  (K / 100 · Tol)          /  (L · s)        = 0.2 · Tol / (6 · s)
    Cgk  =  ((K / 200) · Tol − |x̄ − xₘ|) / ((L/2) · s) = (0.1 · Tol − bias) / (3 · s)

with the Minitab defaults K = 20, L = 6.

Interpretation
--------------
Cg  answers: "How *precise* is the system?"  (ignores bias, purely scatter
            vs. tolerance)
Cgk answers: "How precise **and accurate** is the system?"  (penalises
            the offset of the mean from the reference value)

A system is considered capable when **both** Cg and Cgk ≥ 1.33.  For a
well-calibrated system Cg ≈ Cgk (mean sits on reference).

This service is pure numpy — no DB access, no GUI, fully unit-testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MSAReport:
    """
    Immutable Type-1 gage-study report.

    Attributes
    ----------
    material
        Free-form label for identification in UI / CSV export
        (e.g. "Cu @ 635 nm (multi, corrected)").
    reference_thickness
        The reference (true) thickness xₘ of the test sample, in nm.
    tolerance
        Total tolerance band Tol for the part being measured, in nm.
        e.g. for a "±65 nm" specification, pass tolerance=130.
    n
        Number of repeated measurements included in the study.
    mean, std
        Sample mean x̄ and sample standard deviation s (ddof=1).
    bias
        |x̄ − xₘ|, the magnitude of systematic deviation.
    cg, cgk
        Capability indices (see module docstring).
    capable_threshold
        Threshold above which Cg and Cgk are considered capable (default
        1.33 per Minitab / industry convention).
    cg_capable, cgk_capable, is_capable
        Boolean flags for quick UI rendering.
    K, L
        The formula parameters used (stored so a report can be
        reproduced exactly).
    """
    material:            str
    reference_thickness: float
    tolerance:           float
    n:                   int
    mean:                float
    std:                 float
    bias:                float
    cg:                  float
    cgk:                 float
    capable_threshold:   float
    cg_capable:          bool
    cgk_capable:         bool
    is_capable:          bool
    K:                   int
    L:                   int

    # ------------------------------------------------------------------
    # Rendering helpers (used by the validation page and CSV export)
    # ------------------------------------------------------------------

    def summary(self) -> str:
        status = "CAPABLE ✓" if self.is_capable else "NOT CAPABLE ✗"
        return (
            f"MSA Typ 1 — {self.material} @ {self.reference_thickness:g} nm\n"
            f"  n={self.n}  x̄={self.mean:.4f}  s={self.std:.4f}  "
            f"bias={self.bias:.4f}\n"
            f"  Cg={self.cg:.3f}  Cgk={self.cgk:.3f}  "
            f"(threshold = {self.capable_threshold:.2f})  →  {status}"
        )

    def to_dict(self) -> dict:
        """JSON/CSV-friendly representation."""
        return asdict(self)


class MSAService:
    """
    Computes MSA Typ 1 capability indices.

    The service is stateless — every call to :meth:`compute` produces
    an independent :class:`MSAReport`.

    Usage
    -----
    >>> svc = MSAService()
    >>> report = svc.compute(
    ...     measurements        = [29.8, 30.1, 30.2, …],
    ...     reference_thickness = 30.0,
    ...     tolerance           = 130.0,     # ±65 nm
    ...     material            = "Cu, 30 nm, multi, raw",
    ... )
    >>> report.summary()

    For before/after calibration comparisons use :meth:`compare`.
    """

    # Minitab defaults, also used in BA1/BA2.
    K_DEFAULT:                 int   = 20     # % of Tol reserved for scatter
    L_DEFAULT:                 int   = 6      # σ-multiplier (6σ ≈ 99.73 %)
    CAPABLE_THRESHOLD_DEFAULT: float = 1.33

    # Minimum number of repeated measurements required for a meaningful
    # Type-1 study (Minitab and ISO 22514-7 both recommend ≥25).
    MIN_N = 10

    def __init__(
        self,
        K:                 int   | None = None,
        L:                 int   | None = None,
        capable_threshold: float | None = None,
    ):
        self.K                 = self.K_DEFAULT                 if K                 is None else K
        self.L                 = self.L_DEFAULT                 if L                 is None else L
        self.capable_threshold = self.CAPABLE_THRESHOLD_DEFAULT if capable_threshold is None else capable_threshold

    # ==================================================================
    # Single study
    # ==================================================================

    def compute(
        self,
        measurements:        list[float] | np.ndarray,
        reference_thickness: float,
        tolerance:           float,
        material:            str = "",
    ) -> MSAReport:
        """
        Runs one Type-1 study on *measurements* repeated at
        *reference_thickness* and produces a report.

        Raises
        ------
        ValueError
            If fewer than :attr:`MIN_N` measurements are supplied or if
            the tolerance is non-positive.
        """
        x = np.asarray(measurements, dtype=np.float64)
        if x.size < self.MIN_N:
            raise ValueError(
                f"Need at least {self.MIN_N} measurements for MSA Typ 1, "
                f"got {x.size}"
            )
        if tolerance <= 0:
            raise ValueError(f"Tolerance must be > 0, got {tolerance}")

        n     = int(x.size)
        mean  = float(x.mean())
        std   = float(x.std(ddof=1)) if n > 1 else 0.0
        bias  = abs(mean - reference_thickness)

        cg, cgk = self._capability_indices(
            std=std, bias=bias, tolerance=tolerance,
        )

        cg_capable  = cg  >= self.capable_threshold
        cgk_capable = cgk >= self.capable_threshold

        report = MSAReport(
            material            = material,
            reference_thickness = float(reference_thickness),
            tolerance           = float(tolerance),
            n                   = n,
            mean                = mean,
            std                 = std,
            bias                = bias,
            cg                  = round(cg,  4),
            cgk                 = round(cgk, 4),
            capable_threshold   = self.capable_threshold,
            cg_capable          = cg_capable,
            cgk_capable         = cgk_capable,
            is_capable          = cg_capable and cgk_capable,
            K                   = self.K,
            L                   = self.L,
        )
        logger.info(report.summary().replace("\n", " | "))
        return report

    # ==================================================================
    # Before / after comparison
    # ==================================================================

    def compare(
        self,
        raw:                 list[float] | np.ndarray,
        corrected:           list[float] | np.ndarray,
        reference_thickness: float,
        tolerance:           float,
        material:            str = "",
    ) -> dict[str, MSAReport]:
        """
        Runs MSA Typ 1 twice — once on the raw Lambert-Beer output and
        once on the calibration-corrected values — and returns both
        reports in a dict.

        This is the core numeric output of the BA2 validation page.

        Returns
        -------
        {'raw': MSAReport, 'corrected': MSAReport}
        """
        raw_arr = np.asarray(raw,       dtype=np.float64)
        cor_arr = np.asarray(corrected, dtype=np.float64)

        if raw_arr.shape != cor_arr.shape:
            raise ValueError(
                f"Raw and corrected arrays must be the same length "
                f"({raw_arr.size} vs {cor_arr.size})"
            )

        return {
            "raw": self.compute(
                raw_arr, reference_thickness, tolerance,
                material=f"{material} (raw)".strip(),
            ),
            "corrected": self.compute(
                cor_arr, reference_thickness, tolerance,
                material=f"{material} (corrected)".strip(),
            ),
        }

    # ==================================================================
    # Internal
    # ==================================================================

    def _capability_indices(
        self, std: float, bias: float, tolerance: float,
    ) -> tuple[float, float]:
        """
        Applies the MSA Typ 1 formulae, guarding against s = 0.

        When s is zero every measurement is identical — mathematically
        the indices are infinite, but returning +inf breaks JSON
        serialisation in the report.  We return a large sentinel (1e6)
        so the UI / DB still render it as "very capable".
        """
        if std == 0.0:
            sentinel = 1.0e6
            logger.debug(
                "MSA: std == 0 — returning sentinel capability %g", sentinel
            )
            return sentinel, sentinel

        cg  = (self.K / 100.0 * tolerance)            / (self.L * std)
        cgk = ((self.K / 200.0) * tolerance - bias)   / ((self.L / 2.0) * std)
        return cg, cgk