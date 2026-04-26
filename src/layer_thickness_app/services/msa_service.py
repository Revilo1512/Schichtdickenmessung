"""
Measurement System Analysis — Type 1 (Gage Study).

Two capability indices are computed:

    Cg   = (K/100 · Tol)            / (L · s)         = 0.2 · Tol / (6 · s)
    Cgk  = ((K/200) · Tol − |x̄ − xₘ|) / ((L/2) · s)    = (0.1 · Tol − bias) / (3 · s)

with the Minitab defaults K = 20, L = 6.

A system is considered capable when both Cg and Cgk are ≥ 1.33.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MSAReport:
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

    def summary(self) -> str:
        status = "CAPABLE ✓" if self.is_capable else "NOT CAPABLE ✗"
        return (
            f"MSA Type 1 — {self.material} @ {self.reference_thickness:g} nm\n"
            f"  n={self.n}  x̄={self.mean:.4f}  s={self.std:.4f}  "
            f"bias={self.bias:.4f}\n"
            f"  Cg={self.cg:.3f}  Cgk={self.cgk:.3f}  "
            f"(threshold = {self.capable_threshold:.2f})  →  {status}"
        )

    def to_dict(self) -> dict:
        return asdict(self)


class MSAService:
    """Stateless MSA Type 1 capability calculator."""

    K_DEFAULT:                 int   = 20
    L_DEFAULT:                 int   = 6
    CAPABLE_THRESHOLD_DEFAULT: float = 1.33

    # Minimum repeated measurements for a meaningful Type 1 study.
    # Minitab and ISO 22514-7 both recommend 25.
    MIN_N = 25

    def __init__(
        self,
        K:                 int   | None = None,
        L:                 int   | None = None,
        capable_threshold: float | None = None,
    ):
        self.K                 = self.K_DEFAULT                 if K                 is None else K
        self.L                 = self.L_DEFAULT                 if L                 is None else L
        self.capable_threshold = self.CAPABLE_THRESHOLD_DEFAULT if capable_threshold is None else capable_threshold

    def compute(
        self,
        measurements:        list[float] | np.ndarray,
        reference_thickness: float,
        tolerance:           float,
        material:            str = "",
    ) -> MSAReport:
        x = np.asarray(measurements, dtype=np.float64)
        if x.size < self.MIN_N:
            raise ValueError(
                f"Need at least {self.MIN_N} measurements for MSA Type 1, "
                f"got {x.size}"
            )
        if tolerance <= 0:
            raise ValueError(f"Tolerance must be > 0, got {tolerance}")

        n     = int(x.size)
        mean  = float(x.mean())
        std   = float(x.std(ddof=1)) if n > 1 else 0.0
        bias  = abs(mean - reference_thickness)

        cg, cgk = self._capability_indices(std=std, bias=bias, tolerance=tolerance)

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

    def compare(
        self,
        raw:                 list[float] | np.ndarray,
        corrected:           list[float] | np.ndarray,
        reference_thickness: float,
        tolerance:           float,
        material:            str = "",
    ) -> dict[str, MSAReport]:
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

    def _capability_indices(
        self, std: float, bias: float, tolerance: float,
    ) -> tuple[float, float]:
        """
        Returns ``(Cg, Cgk)``. When ``std`` is zero a large sentinel is
        returned so JSON serialisation stays valid.
        """
        if std == 0.0:
            sentinel = 1.0e6
            logger.debug("MSA: std == 0 — returning sentinel capability %g", sentinel)
            return sentinel, sentinel
        cg  = (self.K / 100.0 * tolerance)          / (self.L * std)
        cgk = ((self.K / 200.0) * tolerance - bias) / ((self.L / 2.0) * std)
        return cg, cgk