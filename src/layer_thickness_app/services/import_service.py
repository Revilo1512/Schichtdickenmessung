"""
Import measurement data from a ZIP archive (produced by
``ExportService``) back into the database.
"""

from __future__ import annotations

import csv
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from layer_thickness_app.services.database_service import (
    DatabaseService,
    VALID_COLUMNS,
)

logger = logging.getLogger(__name__)


class ImportService:
    """
    Imports measurement data from a ZIP archive.

    Expected archive layout:
      - ``measurements.csv``
      - ``img/`` containing the referenced image files

    The importer preserves the original stored image filenames so an
    export/import round-trip is byte-identical.
    """

    REQUIRED = frozenset({
        "Layer", "RefImage", "MatImage", "Shelf", "Book", "Page",
    })

    # Numeric optional columns — coerced per-cell so a single bad value
    # only loses that cell, not the whole row.
    _FLOAT_COLUMNS = frozenset({
        "Wavelength", "ReferenceThickness", "ThicknessCorrected",
        "MeanGrayRef", "MeanGraySample", "StdGrayRef", "StdGraySample",
        "HotspotRef", "HotspotSample",
        "SaturatedFractionRef", "SaturatedFractionSample",
    })
    _INT_COLUMNS = frozenset({
        "FrameCountRef", "FrameCountSample", "RunIndex",
    })

    def __init__(self, db_service: DatabaseService):
        self.db_service     = db_service
        self.image_dir_path = self.db_service.image_dir_path

    # ------------------------------------------------------------------

    def import_from_zip(self, zip_filepath: str | Path) -> tuple[int, int]:
        """
        Reads a ZIP archive, copies images to the data/images folder
        and imports metadata into the database.

        Returns ``(success_count, fail_count)``.
        """
        zip_path = Path(zip_filepath)
        logger.info("Starting import from %s", zip_path)
        success_count = 0
        fail_count    = 0
        temp_dir      = Path(tempfile.mkdtemp())

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            csv_path = temp_dir / "measurements.csv"
            if not csv_path.exists():
                logger.error("'measurements.csv' not found in the ZIP file.")
                return (0, 0)

            csv.field_size_limit(10_485_760)

            with csv_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                if not reader.fieldnames:
                    logger.error("CSV file is empty or has no header: %s", csv_path)
                    return (0, 0)

                missing = self.REQUIRED - set(reader.fieldnames)
                if missing:
                    logger.error("CSV is missing required columns: %s", missing)
                    return (0, 0)

                for i, row in enumerate(reader, start=2):
                    if self._process_row(i, row, temp_dir):
                        success_count += 1
                    else:
                        fail_count += 1

        except FileNotFoundError:
            logger.error("File not found at %s", zip_path)
            return (0, 0)
        except zipfile.BadZipFile:
            logger.error("Bad ZIP file %s", zip_path)
            return (0, 0)
        except Exception as e:
            logger.exception("Error reading ZIP file %s: %s", zip_path, e)
            return (0, 0)
        finally:
            try:
                shutil.rmtree(temp_dir)
                logger.debug("Cleaned up temp directory: %s", temp_dir)
            except OSError as e:
                logger.warning("Error cleaning up temp directory %s: %s", temp_dir, e)

        logger.info(
            "Import complete: %d rows succeeded, %d rows failed.",
            success_count, fail_count,
        )
        return (success_count, fail_count)

    # ------------------------------------------------------------------

    def _process_row(self, i: int, row: dict[str, str], temp_dir: Path) -> bool:
        """Process one CSV row. Returns True on success."""
        try:
            data_to_save: dict[str, Any] = {}

            # Required: Layer must parse as float.
            try:
                data_to_save["Layer"] = float(row["Layer"])
            except (ValueError, TypeError):
                logger.warning(
                    "Row %d: invalid 'Layer' value '%s' — skipping row.",
                    i, row.get("Layer", "N/A"),
                )
                return False

            # Required: material path triple.
            for col in ("Shelf", "Book", "Page"):
                val = row.get(col)
                if not val:
                    logger.warning(
                        "Row %d: missing required column '%s' — skipping row.",
                        i, col,
                    )
                    return False
                data_to_save[col] = val

            # Text-like optional columns pass through verbatim.
            text_optional = (
                VALID_COLUMNS - self.REQUIRED
                - self._FLOAT_COLUMNS - self._INT_COLUMNS
                - {"id", "RefImage", "MatImage"}
            )
            for col in text_optional:
                if col in row and row[col] != "":
                    data_to_save[col] = row[col]

            # Numeric optional columns — coerce per-cell.
            for col in self._FLOAT_COLUMNS:
                raw_val = row.get(col)
                if raw_val is None or raw_val == "":
                    continue
                try:
                    data_to_save[col] = float(raw_val)
                except (ValueError, TypeError):
                    logger.warning(
                        "Row %d: could not parse '%s' as float (got '%s') — "
                        "column skipped.", i, col, raw_val,
                    )

            for col in self._INT_COLUMNS:
                raw_val = row.get(col)
                if raw_val is None or raw_val == "":
                    continue
                try:
                    data_to_save[col] = int(float(raw_val))   # tolerate "30.0"
                except (ValueError, TypeError):
                    logger.warning(
                        "Row %d: could not parse '%s' as int (got '%s') — "
                        "column skipped.", i, col, raw_val,
                    )

            # Image bytes — preserve the stored filenames.
            ref_img_rel = row.get("RefImage")
            mat_img_rel = row.get("MatImage")
            if not ref_img_rel or not mat_img_rel:
                logger.warning("Row %d: missing RefImage or MatImage path.", i)
                return False

            ref_img_src = temp_dir / ref_img_rel
            mat_img_src = temp_dir / mat_img_rel
            if not ref_img_src.exists() or not mat_img_src.exists():
                logger.warning(
                    "Row %d: image file not found in ZIP. Expected %s and %s.",
                    i, ref_img_src, mat_img_src,
                )
                return False

            # The DB stores the filename only (no directory prefix).
            ref_img_name = Path(ref_img_rel).name
            mat_img_name = Path(mat_img_rel).name

            try:
                shutil.copy(ref_img_src, self.image_dir_path / ref_img_name)
                shutil.copy(mat_img_src, self.image_dir_path / mat_img_name)
            except OSError as e:
                logger.warning("Row %d: could not copy image files (%s).", i, e)
                return False

            data_to_save["RefImage"] = ref_img_name
            data_to_save["MatImage"] = mat_img_name

            new_id = self.db_service.save_measurement(data_to_save)
            if new_id <= 0:
                logger.warning("Row %d: database save failed.", i)
                return False

            return True

        except Exception as e:
            logger.exception("Row %d: unexpected error — %s", i, e)
            return False