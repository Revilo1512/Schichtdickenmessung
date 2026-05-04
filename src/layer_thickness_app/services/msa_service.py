"""
Measurement System Analysis — Type 1 (Gage Study).

Capability indices (Minitab / ISO 22514-7 conventions):

    Cg   = (K/100 · Tol)            / (L · s)         = 0.2 · Tol / (6 · s)
    Cgk  = ((K/200) · Tol − |x̄ − xₘ|) / ((L/2) · s)    = (0.1 · Tol − bias) / (3 · s)

with the Minitab defaults K = 20, L = 6.

Variation aggregates (Minitab / ISO 22514-7):

    %Var(repeatability)        =  6 · s / Tol · 100 %
    %Var(repeatability + bias) =  √((6·s)² + (2·|bias|)²) / Tol · 100 %

Bias significance: a one-sample t-test of (x_i − x_ref) against zero,
matching the "Test syst. Mssabw=0" line in the standard Minitab report.

A system is considered capable when both Cg and Cgk are ≥ 1.33.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, asdict

import numpy as np

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except Exception:
    _HAS_SCIPY = False

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MSAReport:
    material:                 str
    reference_thickness:      float
    tolerance:                float
    n:                        int
    mean:                     float
    std:                      float
    bias:                     float
    cg:                       float
    cgk:                      float
    pct_var_repeat:           float
    pct_var_repeat_and_bias:  float
    t_stat:                   float
    p_value:                  float
    capable_threshold:        float
    cg_capable:               bool
    cgk_capable:              bool
    is_capable:               bool
    K:                        int
    L:                        int

    def summary(self) -> str:
        status = "CAPABLE ✓" if self.is_capable else "NOT CAPABLE ✗"
        return (
            f"MSA Type 1 — {self.material} @ {self.reference_thickness:g} nm\n"
            f"  n={self.n}  x̄={self.mean:.4f}  s={self.std:.4f}  "
            f"bias={self.bias:.4f}\n"
            f"  Cg={self.cg:.3f}  Cgk={self.cgk:.3f}  "
            f"(threshold = {self.capable_threshold:.2f})  →  {status}\n"
            f"  %Var(repeat)={self.pct_var_repeat:.2f} %  "
            f"%Var(repeat+bias)={self.pct_var_repeat_and_bias:.2f} %\n"
            f"  bias t-test: t={self.t_stat:.3f}, p={self.p_value:.4f}"
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
        pct_repeat, pct_repeat_bias = self._pct_var(
            std=std, bias=bias, tolerance=tolerance,
        )
        t_stat, p_value = self._bias_ttest(x=x, reference=reference_thickness)

        cg_capable  = cg  >= self.capable_threshold
        cgk_capable = cgk >= self.capable_threshold

        report = MSAReport(
            material                = material,
            reference_thickness     = float(reference_thickness),
            tolerance               = float(tolerance),
            n                       = n,
            mean                    = mean,
            std                     = std,
            bias                    = bias,
            cg                      = round(cg,  4),
            cgk                     = round(cgk, 4),
            pct_var_repeat          = round(pct_repeat,      4),
            pct_var_repeat_and_bias = round(pct_repeat_bias, 4),
            t_stat                  = round(t_stat,          4),
            p_value                 = round(p_value,         6),
            capable_threshold       = self.capable_threshold,
            cg_capable              = cg_capable,
            cgk_capable             = cgk_capable,
            is_capable              = cg_capable and cgk_capable,
            K                       = self.K,
            L                       = self.L,
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

    # ------------------------------------------------------------------
    # Cross-mode precision comparison (Single-Frame vs Multi-Frame).
    # Welch's t-test on the absolute deviations from the reference is a
    # simple way to quantify whether one mode is meaningfully more
    # precise; equal-variance assumption is dropped because the two
    # modes have different noise profiles by construction.
    # ------------------------------------------------------------------
    def compare_precision(
        self,
        single_frame: list[float] | np.ndarray,
        multi_frame:  list[float] | np.ndarray,
        reference_thickness: float,
    ) -> dict[str, float]:
        s = np.asarray(single_frame, dtype=np.float64)
        m = np.asarray(multi_frame,  dtype=np.float64)
        if s.size < 2 or m.size < 2:
            raise ValueError("Need at least two measurements per mode.")

        std_single = float(s.std(ddof=1))
        std_multi  = float(m.std(ddof=1))
        ratio = std_single / std_multi if std_multi > 0 else float("inf")

        # F-test for variance equality. A large F (single more variable
        # than multi) with p < 0.05 confirms the precision improvement.
        var_s = std_single ** 2
        var_m = std_multi  ** 2
        if var_m > 0:
            f_stat = var_s / var_m
            df1, df2 = s.size - 1, m.size - 1
            if _HAS_SCIPY:
                p_f = 1.0 - _scipy_stats.f.cdf(f_stat, df1, df2)
            else:
                p_f = float("nan")
        else:
            f_stat = float("inf")
            p_f    = 0.0

        return {
            "std_single": std_single,
            "std_multi":  std_multi,
            "ratio":      ratio,
            "f_stat":     float(f_stat),
            "p_value":    float(p_f),
        }

    # ------------------------------------------------------------------
    # Internal math
    # ------------------------------------------------------------------

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

    @staticmethod
    def _pct_var(
        std: float, bias: float, tolerance: float,
    ) -> tuple[float, float]:
        """
        Type-1 %Var per Minitab / ISO 22514-7.
            repeatability:           6·s              / T · 100 %
            repeatability and bias:  √((6·s)² + (2·|bias|)²) / T · 100 %
        """
        if tolerance <= 0:
            return 0.0, 0.0
        pct_repeat      = (6.0 * std) / tolerance * 100.0
        pct_repeat_bias = (
            math.sqrt((6.0 * std) ** 2 + (2.0 * bias) ** 2) / tolerance * 100.0
        )
        return pct_repeat, pct_repeat_bias

    @staticmethod
    def _bias_ttest(
        x: np.ndarray, reference: float,
    ) -> tuple[float, float]:
        """One-sample t-test of (x - reference) against zero."""
        n = x.size
        if n < 2:
            return 0.0, 1.0

        diffs = x - reference
        mean_diff = float(diffs.mean())
        s = float(diffs.std(ddof=1))
        if s == 0.0:
            return float("inf") if mean_diff != 0.0 else 0.0, 0.0 if mean_diff != 0.0 else 1.0

        t_stat = mean_diff / (s / math.sqrt(n))

        if _HAS_SCIPY:
            p_value = float(2.0 * (1.0 - _scipy_stats.t.cdf(abs(t_stat), df=n - 1)))
        else:
            # Normal-approximation fallback when scipy isn't available.
            # Acceptable for n >= 25; documented in the report.
            p_value = float(2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_stat) / math.sqrt(2.0)))))

        return float(t_stat), float(p_value)