"""
Linearity study across multiple reference thicknesses.

Plots the systematic deviation
(x_meas − x_ref) against x_ref over the full thickness range and fits
a regression line. The linearity figure-of-merit is:

    Linearität = |slope| · Prozessstreuung     

where the process spread is 6 · σ_pooled across all thicknesses. A flat
regression (low |slope|) means the systematic deviation is constant
over the range, which is the desirable behaviour and exactly what the
linear correction in ``calibration_service`` is supposed to produce.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Iterable

import numpy as np

from layer_thickness_app.services.msa_service import MSAReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LinearityPoint:
    reference_thickness: float
    n:                   int
    mean:                float
    std:                 float
    bias_signed:         float


@dataclass(frozen=True)
class LinearityReport:
    material:        str
    label:           str
    points:          list[LinearityPoint] = field(default_factory=list)
    slope:           float = 0.0
    intercept:       float = 0.0
    r_squared:       float = 0.0
    sigma_pooled:    float = 0.0
    linearity_index: float = 0.0
    bias_avg:        float = 0.0
    bias_max:        float = 0.0
    n_total:         int   = 0

    def summary(self) -> str:
        rows = "\n".join(
            f"    ref={p.reference_thickness:>6.1f} nm  "
            f"n={p.n:>3d}  x̄={p.mean:>8.3f}  s={p.std:>7.4f}  "
            f"bias={p.bias_signed:>+7.3f}"
            for p in self.points
        )
        return (
            f"Linearity — {self.label}\n"
            f"{rows}\n"
            f"  slope={self.slope:.4f}  intercept={self.intercept:.4f}  "
            f"R²={self.r_squared:.4f}\n"
            f"  σ_pooled={self.sigma_pooled:.4f}  "
            f"Linearität=|slope|·6·σ={self.linearity_index:.4f}\n"
            f"  bias avg={self.bias_avg:+.3f}  bias max|.|={self.bias_max:.3f}"
        )

    def to_dict(self) -> dict:
        return asdict(self)


class LinearityService:
    """Aggregates per-thickness MSA reports into a single linearity report."""

    MIN_POINTS = 3

    def compute(
        self,
        reports:  Iterable[MSAReport],
        material: str = "",
        label:    str = "",
    ) -> LinearityReport:
        pts: list[LinearityPoint] = []
        for r in reports:
            pts.append(LinearityPoint(
                reference_thickness = float(r.reference_thickness),
                n                   = int(r.n),
                mean                = float(r.mean),
                std                 = float(r.std),
                # Signed bias for the regression; r.bias is absolute.
                bias_signed         = float(r.mean - r.reference_thickness),
            ))

        pts.sort(key=lambda p: p.reference_thickness)

        if len(pts) < self.MIN_POINTS:
            raise ValueError(
                f"Linearity needs at least {self.MIN_POINTS} reference "
                f"thicknesses, got {len(pts)}"
            )

        x = np.asarray([p.reference_thickness for p in pts], dtype=np.float64)
        y = np.asarray([p.bias_signed         for p in pts], dtype=np.float64)

        slope, intercept = np.polyfit(x, y, 1)
        y_hat = slope * x + intercept
        ss_res = float(((y - y_hat) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

        # Pooled std across the per-thickness samples (Welford-equivalent
        # via the standard pooled-variance formula).
        n_total = sum(p.n for p in pts)
        if n_total > len(pts):
            num = sum((p.n - 1) * p.std ** 2 for p in pts)
            den = n_total - len(pts)
            sigma_pooled = float(np.sqrt(num / den)) if den > 0 else 0.0
        else:
            sigma_pooled = 0.0

        linearity_index = float(abs(slope) * 6.0 * sigma_pooled)
        bias_avg = float(np.mean(y))
        bias_max = float(np.max(np.abs(y)))

        report = LinearityReport(
            material        = material,
            label           = label or material,
            points          = pts,
            slope           = float(slope),
            intercept       = float(intercept),
            r_squared       = float(r_squared),
            sigma_pooled    = sigma_pooled,
            linearity_index = linearity_index,
            bias_avg        = bias_avg,
            bias_max        = bias_max,
            n_total         = n_total,
        )
        logger.info(report.summary().replace("\n", " | "))
        return report