"""
Linear regression correction for transmission-based thickness measurements.

The Beer-Lambert calculation in ``calculation_service.py`` ignores
reflection losses at the metal surface and other systematic biases of
the optical path. This module provides an empirical correction:

    y = beta_1 * x + beta_0

where x is the raw Beer-Lambert output and y is the known reference
thickness. The fit is run once per (material, wavelength, mode) from a
batch of calibration samples whose true thickness is known. The fitted
model is persisted and applied at measurement time to produce
``ThicknessCorrected``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from layer_thickness_app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationModel:
    """
    Fitted linear correction: y = slope * x + intercept.

    A model is only valid for the exact (shelf, book, page, wavelength,
    mode) tuple it was fitted on; multi-frame and single-frame have
    different noise characteristics and need separate calibrations.
    """
    slope:         float
    intercept:     float
    r_squared:     float
    n_samples:     int
    shelf:         str
    book:          str
    page:          str
    wavelength_um: float
    mode:          str
    min_ref_nm:    float
    max_ref_nm:    float
    name:          str        = ""
    session_tag:   str | None = None
    note:          str        = ""
    id:            int | None = None

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept

    def predict_array(self, x: np.ndarray) -> np.ndarray:
        return self.slope * x + self.intercept

    def is_in_range(self, x: float, tolerance: float = 5.0) -> bool:
        return (self.min_ref_nm - tolerance) <= x <= (self.max_ref_nm + tolerance)

    def summary(self) -> str:
        return (
            f"{self.book}/{self.page} @ {self.wavelength_um} um "
            f"[{self.mode}] -- slope={self.slope:.4f}, "
            f"intercept={self.intercept:.4f}, R^2={self.r_squared:.4f}, "
            f"n={self.n_samples}"
        )


# ---------------------------------------------------------------------------

class CalibrationService:
    """Fits and applies linear correction models. Stateless."""

    # Below this many points the linear fit is under-determined.
    MIN_POINTS_FOR_FIT = 4

    def __init__(self, db_service: "DatabaseService | None" = None):
        self.db_service = db_service

    # ==================================================================
    # Fitting
    # ==================================================================

    def fit(
        self,
        measured:      list[float] | np.ndarray,
        reference:     list[float] | np.ndarray,
        shelf:         str,
        book:          str,
        page:          str,
        wavelength_um: float,
        mode:          str,
        name:          str        = "",
        session_tag:   str | None = None,
        note:          str        = "",
    ) -> CalibrationModel:
        x = np.asarray(measured,  dtype=np.float64)
        y = np.asarray(reference, dtype=np.float64)

        if x.shape != y.shape:
            raise ValueError(
                f"Length mismatch: {len(x)} measured vs {len(y)} reference"
            )
        if len(x) < self.MIN_POINTS_FOR_FIT:
            raise ValueError(
                f"Need at least {self.MIN_POINTS_FOR_FIT} points, got {len(x)}"
            )
        if np.allclose(x, x[0]):
            raise ValueError(
                "All measured values are identical -- cannot fit a slope. "
                "Include samples with different reference thicknesses."
            )

        slope, intercept = np.polyfit(x, y, deg=1)

        y_pred  = slope * x + intercept
        ss_res  = float(np.sum((y - y_pred) ** 2))
        ss_tot  = float(np.sum((y - y.mean()) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        model = CalibrationModel(
            slope         = float(slope),
            intercept     = float(intercept),
            r_squared     = r_squared,
            n_samples     = int(len(x)),
            shelf         = shelf,
            book          = book,
            page          = page,
            wavelength_um = float(wavelength_um),
            mode          = mode,
            min_ref_nm    = float(y.min()),
            max_ref_nm    = float(y.max()),
            name          = name,
            session_tag   = session_tag,
            note          = note,
        )
        logger.info("Fitted calibration: %s", model.summary())
        return model

    def fit_from_rows(
        self,
        rows:          list[dict[str, Any]],
        shelf:         str,
        book:          str,
        page:          str,
        wavelength_um: float,
        mode:          str,
        name:          str        = "",
        session_tag:   str | None = None,
        note:          str        = "",
    ) -> CalibrationModel:
        """
        Pull (Layer, ReferenceThickness) pairs out of DB rows and fit.
        Rows whose Mode does not match the requested ``mode`` are
        skipped; mixing single- and multi-frame data invalidates the
        model.
        """
        measured:  list[float] = []
        reference: list[float] = []
        for r in rows:
            if r.get("ReferenceThickness") is None or r.get("Layer") is None:
                continue
            if mode and r.get("Mode") and r["Mode"] != mode:
                continue
            measured.append(r["Layer"])
            reference.append(r["ReferenceThickness"])

        if not measured:
            raise ValueError(
                f"No usable calibration rows after filtering (mode='{mode}')."
            )

        return self.fit(
            measured=measured, reference=reference,
            shelf=shelf, book=book, page=page,
            wavelength_um=wavelength_um, mode=mode,
            name=name, session_tag=session_tag, note=note,
        )

    def fit_from_db(
        self,
        shelf:         str,
        book:          str,
        page:          str,
        wavelength_um: float,
        mode:          str,
        session_tag:   str | None = None,
        probe:         str | None = None,
        name:          str        = "",
        note:          str        = "",
    ) -> CalibrationModel:
        self._require_db()
        rows = self.db_service.get_calibration_rows(
            book=book, page=page, session_tag=session_tag, probe=probe,
            wavelength_um=wavelength_um, mode=mode,
        )
        return self.fit_from_rows(
            rows, shelf=shelf, book=book, page=page,
            wavelength_um=wavelength_um, mode=mode,
            name=name, session_tag=session_tag, note=note,
        )

    # ==================================================================
    # Train / test splits
    # ==================================================================

    @staticmethod
    def split_by_measurement(
        rows:        list[dict[str, Any]],
        test_ratio:  float = 0.3,
        random_seed: int | None = 42,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not 0 < test_ratio < 1:
            raise ValueError("test_ratio must be in (0, 1)")

        rng = np.random.default_rng(random_seed)
        idx = np.arange(len(rows))
        rng.shuffle(idx)

        n_test  = int(round(len(rows) * test_ratio))
        test_i  = idx[:n_test]
        train_i = idx[n_test:]
        train = [rows[i] for i in train_i]
        test  = [rows[i] for i in test_i]
        return train, test

    @staticmethod
    def split_by_reference(
        rows:            list[dict[str, Any]],
        test_references: list[float],
        tolerance:       float = 0.5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        train: list[dict[str, Any]] = []
        test:  list[dict[str, Any]] = []
        for row in rows:
            ref = row.get("ReferenceThickness")
            if ref is None:
                continue
            if any(abs(ref - t) <= tolerance for t in test_references):
                test.append(row)
            else:
                train.append(row)
        return train, test

    # ==================================================================
    # Evaluation
    # ==================================================================

    @staticmethod
    def evaluate(
        model:     CalibrationModel,
        measured:  list[float] | np.ndarray,
        reference: list[float] | np.ndarray,
    ) -> dict[str, float]:
        """
        Before/after metrics for ``model`` against a (measured,
        reference) test set. Positive bias means the system reads high;
        a successful calibration drives mean_bias_after towards zero.
        """
        x = np.asarray(measured,  dtype=np.float64)
        y = np.asarray(reference, dtype=np.float64)

        if x.shape != y.shape or len(x) == 0:
            raise ValueError("measured and reference must have same non-zero length")

        y_pred     = model.predict_array(x)
        err_before = x       - y
        err_after  = y_pred  - y

        return {
            "n":                    int(len(x)),
            "mean_bias_before":     float(err_before.mean()),
            "mean_bias_after":      float(err_after.mean()),
            "mae_before":           float(np.abs(err_before).mean()),
            "mae_after":            float(np.abs(err_after).mean()),
            "rmse_before":          float(np.sqrt((err_before ** 2).mean())),
            "rmse_after":           float(np.sqrt((err_after  ** 2).mean())),
            "max_abs_error_before": float(np.abs(err_before).max()),
            "max_abs_error_after":  float(np.abs(err_after).max()),
        }

    # ==================================================================
    # Persistence
    # ==================================================================

    def save(self, model: CalibrationModel, set_active: bool = False) -> int:
        self._require_db()
        data = {
            "Name":       model.name,
            "Shelf":      model.shelf,
            "Book":       model.book,
            "Page":       model.page,
            "Wavelength": model.wavelength_um,
            "Mode":       model.mode,
            "Slope":      model.slope,
            "Intercept":  model.intercept,
            "RSquared":   model.r_squared,
            "NSamples":   model.n_samples,
            "MinRefNm":   model.min_ref_nm,
            "MaxRefNm":   model.max_ref_nm,
            "SessionTag": model.session_tag,
            "Note":       model.note,
        }
        new_id = self.db_service.save_calibration(data)
        if new_id > 0 and set_active:
            self.db_service.set_active_calibration(new_id)
        return new_id

    def load(self, calibration_id: int) -> CalibrationModel | None:
        self._require_db()
        row = self.db_service.get_calibration(calibration_id)
        return self._row_to_model(row) if row else None

    def load_active(
        self, shelf: str, book: str, page: str,
        wavelength_um: float, mode: str,
    ) -> CalibrationModel | None:
        self._require_db()
        row = self.db_service.get_active_calibration(
            shelf=shelf, book=book, page=page,
            wavelength_um=wavelength_um, mode=mode,
        )
        return self._row_to_model(row) if row else None

    def list_models(
        self, *,
        shelf: str | None = None, book: str | None = None,
        page:  str | None = None, wavelength_um: float | None = None,
        mode:  str | None = None, active_only: bool = False,
    ) -> list[CalibrationModel]:
        self._require_db()
        rows = self.db_service.get_calibrations(
            shelf=shelf, book=book, page=page,
            wavelength=wavelength_um, mode=mode,
            active_only=active_only,
        )
        return [self._row_to_model(r) for r in rows]

    # ==================================================================
    # Internal
    # ==================================================================

    def _require_db(self) -> None:
        if self.db_service is None:
            raise RuntimeError(
                "This operation requires a DatabaseService -- pass one to "
                "CalibrationService() at construction time."
            )

    @staticmethod
    def _row_to_model(row: dict[str, Any]) -> CalibrationModel:
        return CalibrationModel(
            id            = row.get("id"),
            slope         = float(row["Slope"]),
            intercept     = float(row["Intercept"]),
            r_squared     = float(row["RSquared"]),
            n_samples     = int(row["NSamples"]),
            shelf         = row["Shelf"],
            book          = row["Book"],
            page          = row["Page"],
            wavelength_um = float(row["Wavelength"]),
            mode          = row["Mode"],
            min_ref_nm    = float(row["MinRefNm"]) if row.get("MinRefNm") is not None else 0.0,
            max_ref_nm    = float(row["MaxRefNm"]) if row.get("MaxRefNm") is not None else 0.0,
            name          = row.get("Name") or "",
            session_tag   = row.get("SessionTag"),
            note          = row.get("Note") or "",
        )