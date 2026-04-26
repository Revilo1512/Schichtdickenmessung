"""
Report export for MSA Type 1 validation studies.

Produces a timestamped ZIP file containing:
  - summary.txt       : human-readable headline with Cg / Cgk verdicts
  - msa_raw.csv       : one-row CSV with the raw-measurements MSA report
  - msa_corrected.csv : one-row CSV with the corrected MSA report (if any)
  - measurements.csv  : the underlying repeated-measurement series
  - calibration.csv   : the calibration model metadata (if any)

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
from typing import Any

from layer_thickness_app.services.msa_service         import MSAReport
from layer_thickness_app.services.calibration_service import CalibrationModel

logger = logging.getLogger(__name__)


class ReportService:
    """Serialises MSA validation studies to disk."""

    # ------------------------------------------------------------------
    # Public API
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
        """
        Writes a full MSA study to a timestamped ZIP in *export_dir*.

        Returns
        -------
        str
            Absolute path to the generated ZIP file, or "" on failure.
        """
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
        """Human-readable headline summary of the MSA study."""
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
        """One-row CSV of an MSAReport."""
        row = asdict(report)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

    @staticmethod
    def _write_measurements_csv(
        path: Path, measurements: list[dict[str, Any]],
    ) -> None:
        """Raw measurement series — exactly what was fed into MSA."""
        if not measurements:
            path.write_text("", encoding="utf-8")
            return

        # Stable column order: useful fields first, then everything else.
        preferred = [
            "id", "Date", "Layer", "ThicknessCorrected",
            "ReferenceThickness", "Mode",
            "FrameCountRef", "FrameCountSample",
            "MeanGrayRef", "MeanGraySample",
            "StdGrayRef", "StdGraySample",
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

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_filename_fragment(text: str) -> str:
        """Turn an arbitrary label into a filesystem-safe filename chunk."""
        keep = []
        for ch in text:
            if ch.isalnum() or ch in "-_":
                keep.append(ch)
            elif ch in (" ", "/", "\\", ".", ","):
                keep.append("_")
        return "".join(keep).strip("_")[:60]


# ---------------------------------------------------------------------------
# Module-level helper kept here (instead of as a static method) so the UI
# layer can import it without dragging the writer code along.
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