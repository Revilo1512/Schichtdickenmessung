"""
Report export for MSA Type 1 validation studies.

``export_msa_study`` writes a timestamped ZIP per (probe, reference)
containing summary, MSA reports, raw measurements and the active
calibration model. ``export_linearity_study`` aggregates several MSA
reports across reference thicknesses (e.g. 30/40/50/60 nm) into a
single linearity ZIP with regression slope, intercept, R² and the
Linearität figure-of-merit.

All files are plain UTF-8 CSV for easy import into Excel, Minitab or
any downstream statistics tool.
"""

from __future__ import annotations

import csv
import datetime
import logging
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from layer_thickness_app.services.msa_service         import MSAReport
from layer_thickness_app.services.calibration_service import CalibrationModel
from layer_thickness_app.services.linearity_service   import (
    LinearityReport, LinearityService,
)

logger = logging.getLogger(__name__)


class ReportService:
    """Serialises MSA validation studies and linearity studies to disk."""

    # ------------------------------------------------------------------
    # Public API — MSA study (single reference thickness)
    # ------------------------------------------------------------------

    def export_msa_study(
        self,
        export_dir:          str | Path,
        raw_report:          MSAReport,
        corrected_report:    MSAReport | None,
        measurements:        list[dict[str, Any]],
        calibration_model:   CalibrationModel | None,
        reference_thickness: float,
        tolerance:           float,
        material_label:      str,
    ) -> str:
        export_dir = Path(export_dir)
        if not export_dir.is_dir():
            logger.error("Export directory does not exist: %s", export_dir)
            return ""

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_material = self._safe_filename_fragment(material_label) or "msa"
        zip_base = export_dir / f"msa_{safe_material}_{stamp}"

        tmp = Path(tempfile.mkdtemp())
        try:
            self._write_summary_txt(
                tmp / "summary.txt",
                raw_report, corrected_report, calibration_model,
                reference_thickness, tolerance, material_label,
            )
            self._write_report_csv(tmp / "msa_raw.csv", raw_report)
            if corrected_report is not None:
                self._write_report_csv(tmp / "msa_corrected.csv", corrected_report)
            self._write_measurements_csv(tmp / "measurements.csv", measurements)
            if calibration_model is not None:
                self._write_calibration_csv(tmp / "calibration.csv", calibration_model)

            zip_path = shutil.make_archive(
                base_name = str(zip_base),
                format    = "zip",
                root_dir  = str(tmp),
            )
            logger.info("Exported MSA study to %s", zip_path)
            return zip_path
        except Exception as e:
            logger.exception("MSA export failed: %s", e)
            return ""
        finally:
            try:
                shutil.rmtree(tmp)
            except OSError as e:
                logger.warning("Could not clean up temp dir %s: %s", tmp, e)

    # ------------------------------------------------------------------
    # Public API — linearity study (across multiple reference thicknesses)
    # ------------------------------------------------------------------

    def export_linearity_study(
        self,
        export_dir:    str | Path,
        reports:       Iterable[MSAReport],
        material_label: str,
    ) -> str:
        export_dir = Path(export_dir)
        if not export_dir.is_dir():
            logger.error("Export directory does not exist: %s", export_dir)
            return ""

        report_list = list(reports)
        if not report_list:
            logger.error("No MSA reports supplied for linearity export.")
            return ""

        try:
            lin_report = LinearityService().compute(
                report_list, material=material_label, label=material_label,
            )
        except Exception as e:
            logger.exception("Linearity computation failed: %s", e)
            return ""

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_material = self._safe_filename_fragment(material_label) or "linearity"
        zip_base = export_dir / f"linearity_{safe_material}_{stamp}"

        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "linearity_summary.txt").write_text(
                lin_report.summary() + "\n", encoding="utf-8",
            )
            self._write_linearity_csv(tmp / "linearity.csv", lin_report)
            for r in report_list:
                fname = (
                    f"msa_ref_{int(round(r.reference_thickness)):d}_nm.csv"
                )
                self._write_report_csv(tmp / fname, r)

            zip_path = shutil.make_archive(
                base_name = str(zip_base),
                format    = "zip",
                root_dir  = str(tmp),
            )
            logger.info("Exported linearity study to %s", zip_path)
            return zip_path
        except Exception as e:
            logger.exception("Linearity export failed: %s", e)
            return ""
        finally:
            try:
                shutil.rmtree(tmp)
            except OSError as e:
                logger.warning("Could not clean up temp dir %s: %s", tmp, e)

    # ------------------------------------------------------------------
    # File writers
    # ------------------------------------------------------------------

    @staticmethod
    def _write_summary_txt(
        path:                Path,
        raw:                 MSAReport,
        corrected:           MSAReport | None,
        calibration:         CalibrationModel | None,
        reference_thickness: float,
        tolerance:           float,
        material_label:      str,
    ) -> None:
        lines: list[str] = []
        lines.append("=" * 72)
        lines.append("MSA Type 1 Validation Report")
        lines.append("=" * 72)
        lines.append(f"Generated         : {datetime.datetime.now().isoformat(timespec='seconds')}")
        lines.append(f"Material          : {material_label}")
        lines.append(f"Reference (xm)    : {reference_thickness:g} nm")
        lines.append(f"Tolerance (Tol)   : {tolerance:g} nm")
        lines.append(f"Capable threshold : {raw.capable_threshold:.2f}")
        lines.append(f"Formula params    : K={raw.K}, L={raw.L}")
        lines.append("")

        lines.append("-" * 72)
        lines.append("RAW (uncorrected Lambert-Beer output)")
        lines.append("-" * 72)
        lines.append(raw.summary())

        if corrected is not None:
            lines.append("")
            lines.append("-" * 72)
            lines.append("CORRECTED (after linear regression)")
            lines.append("-" * 72)
            lines.append(corrected.summary())
            lines.append("")
            lines.append("-" * 72)
            lines.append("VERDICT")
            lines.append("-" * 72)
            lines.append(_verdict_text(raw, corrected))
        else:
            lines.append("")
            lines.append("(no calibration applied — corrected report not generated)")

        if calibration is not None:
            lines.append("")
            lines.append("-" * 72)
            lines.append("CALIBRATION MODEL")
            lines.append("-" * 72)
            lines.append(calibration.summary())
            lines.append(
                f"Fitted range      : "
                f"{calibration.min_ref_nm:g} – {calibration.max_ref_nm:g} nm"
            )
            if calibration.session_tag:
                lines.append(f"Session tag       : {calibration.session_tag}")

        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _write_report_csv(path: Path, report: MSAReport) -> None:
        row = asdict(report)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

    @staticmethod
    def _write_measurements_csv(
        path: Path, measurements: list[dict[str, Any]],
    ) -> None:
        if not measurements:
            path.write_text("", encoding="utf-8")
            return

        preferred = [
            "id", "Date", "Layer", "ThicknessCorrected",
            "ReferenceThickness", "Mode",
            "FrameCountRef", "FrameCountSample",
            "MeanGrayRef", "MeanGraySample",
            "StdGrayRef", "StdGraySample",
            "HotspotRef", "HotspotSample",
            "SaturatedFractionRef", "SaturatedFractionSample",
            "SessionTag", "Probe", "RunIndex",
        ]
        all_keys: list[str] = []
        seen: set[str] = set()
        for k in preferred:
            if k in measurements[0]:
                all_keys.append(k); seen.add(k)
        for k in measurements[0].keys():
            if k not in seen:
                all_keys.append(k)

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for m in measurements:
                writer.writerow({k: m.get(k) for k in all_keys})

    @staticmethod
    def _write_calibration_csv(path: Path, model: CalibrationModel) -> None:
        row = asdict(model)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

    @staticmethod
    def _write_linearity_csv(path: Path, report: LinearityReport) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "material", "label",
                "slope", "intercept", "r_squared",
                "sigma_pooled", "linearity_index",
                "bias_avg", "bias_max", "n_total",
            ])
            writer.writerow([
                report.material, report.label,
                report.slope, report.intercept, report.r_squared,
                report.sigma_pooled, report.linearity_index,
                report.bias_avg, report.bias_max, report.n_total,
            ])
            writer.writerow([])
            writer.writerow([
                "reference_thickness", "n", "mean", "std", "bias_signed",
            ])
            for p in report.points:
                writer.writerow([
                    p.reference_thickness, p.n, p.mean, p.std, p.bias_signed,
                ])

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_filename_fragment(text: str) -> str:
        keep = []
        for ch in text:
            if ch.isalnum() or ch in "-_":
                keep.append(ch)
            elif ch in (" ", "/", "\\", ".", ","):
                keep.append("_")
        return "".join(keep).strip("_")[:60]


# ---------------------------------------------------------------------------

def _verdict_text(raw: MSAReport, corrected: MSAReport) -> str:
    if corrected.is_capable and not raw.is_capable:
        headline = "Calibration made the system CAPABLE."
    elif corrected.is_capable and raw.is_capable:
        headline = "System capable before and after."
    elif not corrected.is_capable and raw.is_capable:
        headline = "Warning: correction REDUCED capability."
    else:
        headline = "System still NOT capable."

    return (
        f"{headline}\n"
        f"  Cgk: {raw.cgk:.3f}  →  {corrected.cgk:.3f}   "
        f"(Δ = {corrected.cgk - raw.cgk:+.3f})\n"
        f"  Bias: {raw.bias:.3f}  →  {corrected.bias:.3f} nm"
    )