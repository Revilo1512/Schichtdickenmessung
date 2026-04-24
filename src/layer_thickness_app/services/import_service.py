from __future__ import annotations

import csv
import logging
import os
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
    Imports measurement data from a ZIP archive into the DatabaseService.

    The ZIP archive is expected to contain:
      - measurements.csv
      - img/ — the referenced image files

    The importer preserves the original stored image filenames so that
    an export/import round-trip is byte-identical.
    """

    # Columns that MUST be present. Everything else is optional.
    REQUIRED = frozenset({
        "Layer", "RefImage", "MatImage", "Shelf", "Book", "Page",
    })

    # Optional numeric columns — coerced to float/int per-column so a
    # single bad value only loses that cell, not the whole row.
    _FLOAT_COLUMNS = frozenset({
        "Wavelength", "ReferenceThickness", "ThicknessCorrected",
        "MeanGrayRef", "MeanGraySample", "StdGrayRef", "StdGraySample",
    })
    _INT_COLUMNS = frozenset({
        "FrameCountRef", "FrameCountSample", "RunIndex",
    })

    def __init__(self, db_service: DatabaseService):
        self.db_service     = db_service
        # Reuse the DB-service-managed images directory instead of
        # recomputing it from the db path.
        self.image_dir_path = self.db_service.image_dir_path

    # ------------------------------------------------------------------

    def import_from_zip(self, zip_filepath: str) -> tuple[int, int]:
        """
        Reads a ZIP archive, copies images to the data/images folder,
        and imports metadata into the database.

        Returns (success_count, fail_count).
        """
        logger.info("Starting import from %s", zip_filepath)
        success_count = 0
        fail_count    = 0
        temp_dir      = tempfile.mkdtemp()

        try:
            with zipfile.ZipFile(zip_filepath, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            csv_path = os.path.join(temp_dir, "measurements.csv")
            if not os.path.exists(csv_path):
                logger.error("'measurements.csv' not found in the ZIP file.")
                return (0, 0)

            csv.field_size_limit(10_485_760)

            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                if not reader.fieldnames:
                    logger.error("CSV file is empty or has no header: %s", csv_path)
                    return (0, 0)

                reader_headers = set(reader.fieldnames)
                missing = self.REQUIRED - reader_headers
                if missing:
                    logger.error("CSV is missing required columns: %s", missing)
                    return (0, 0)

                for i, row in enumerate(reader, start=2):
                    if self._process_row(i, row, temp_dir):
                        success_count += 1
                    else:
                        fail_count += 1

        except FileNotFoundError:
            logger.error("File not found at %s", zip_filepath)
            return (0, 0)
        except zipfile.BadZipFile:
            logger.error("Bad ZIP file %s", zip_filepath)
            return (0, 0)
        except Exception as e:
            logger.exception("Error reading ZIP file %s: %s", zip_filepath, e)
            return (0, 0)
        finally:
            try:
                shutil.rmtree(temp_dir)
                logger.debug("Cleaned up temp directory: %s", temp_dir)
            except Exception as e:
                logger.warning("Error cleaning up temp directory %s: %s", temp_dir, e)

        logger.info(
            "Import complete: %d rows succeeded, %d rows failed.",
            success_count, fail_count,
        )
        return (success_count, fail_count)

    # ------------------------------------------------------------------

    def _process_row(self, i: int, row: dict[str, str], temp_dir: str) -> bool:
        """Process one CSV row — returns True on success."""
        try:
            data_to_save: dict[str, Any] = {}

            # --- Required: Layer must parse ---
            try:
                data_to_save["Layer"] = float(row["Layer"])
            except (ValueError, TypeError):
                logger.warning(
                    "Row %d: invalid 'Layer' value '%s' — skipping row.",
                    i, row.get("Layer", "N/A"),
                )
                return False

            # --- Required: material path ---
            for col in ("Shelf", "Book", "Page"):
                val = row.get(col)
                if not val:
                    logger.warning("Row %d: missing required column '%s' — skipping row.",
                                   i, col)
                    return False
                data_to_save[col] = val

            # --- Copy text-like optional columns through verbatim ---
            text_optional = (VALID_COLUMNS - self.REQUIRED
                             - self._FLOAT_COLUMNS - self._INT_COLUMNS
                             - {"id", "RefImage", "MatImage"})
            for col in text_optional:
                if col in row and row[col] != "":
                    data_to_save[col] = row[col]

            # --- Coerce numeric optional columns ---
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

            # --- Copy image bytes preserving the stored filenames ---
            ref_img_rel_path = row.get("RefImage")
            mat_img_rel_path = row.get("MatImage")
            if not ref_img_rel_path or not mat_img_rel_path:
                logger.warning("Row %d: missing RefImage or MatImage path.", i)
                return False

            ref_img_src_path = os.path.join(temp_dir, ref_img_rel_path)
            mat_img_src_path = os.path.join(temp_dir, mat_img_rel_path)
            if not os.path.exists(ref_img_src_path) or not os.path.exists(mat_img_src_path):
                logger.warning(
                    "Row %d: image file not found in ZIP. "
                    "Expected %s and %s.",
                    i, ref_img_src_path, mat_img_src_path,
                )
                return False

            # The DB stores the filename only (not any "img/" prefix).
            ref_img_name_db = os.path.basename(ref_img_rel_path)
            mat_img_name_db = os.path.basename(mat_img_rel_path)

            ref_img_dest_path = self.image_dir_path / ref_img_name_db
            mat_img_dest_path = self.image_dir_path / mat_img_name_db

            try:
                shutil.copy(ref_img_src_path, ref_img_dest_path)
                shutil.copy(mat_img_src_path, mat_img_dest_path)
            except Exception as e:
                logger.warning("Row %d: could not copy image files (%s).", i, e)
                return False

            data_to_save["RefImage"] = ref_img_name_db
            data_to_save["MatImage"] = mat_img_name_db

            new_id = self.db_service.save_measurement(data_to_save)
            if new_id <= 0:
                logger.warning("Row %d: database save failed.", i)
                return False

            return True

        except Exception as e:
            logger.exception("Row %d: unexpected error — %s", i, e)
            return False