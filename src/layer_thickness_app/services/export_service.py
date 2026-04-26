"""
Export filtered measurement rows (and their referenced images) to a
timestamped ZIP archive.
"""

from __future__ import annotations

import csv
import datetime
import logging
import shutil
import tempfile
from pathlib import Path

from layer_thickness_app.services.database_service import (
    DatabaseService,
    VALID_COLUMNS,
)

logger = logging.getLogger(__name__)

# Export column order. 'id' is dropped; anything missing from this list
# is appended after VALID_COLUMNS so future additions don't get lost.
_PREFERRED_ORDER: tuple[str, ...] = (
    "Date", "Name",
    "Layer", "ThicknessCorrected", "ReferenceThickness",
    "Wavelength", "Mode",
    "Shelf", "Book", "Page",
    "Probe", "RunIndex", "SessionTag",
    "MeanGrayRef", "MeanGraySample", "StdGrayRef", "StdGraySample",
    "FrameCountRef", "FrameCountSample",
    "RefImage", "MatImage",
    "Note",
)


class ExportService:
    """
    Exports measurement data to a timestamped ZIP archive.

    The archive contains ``measurements.csv`` (with ``img/``-relative paths)
    and an ``img/`` folder with the referenced .png files. Stored
    filenames are preserved so an export/import round-trip is
    byte-identical.
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service     = db_service
        self.image_dir_path = self.db_service.image_dir_path

    def export_to_zip(
        self,
        export_dir:  str | Path,
        name_filter: str | None = None,
        start_date:  str | None = None,
        end_date:    str | None = None,
        shelf:       str | None = None,
        book:        str | None = None,
        page:        str | None = None,
        note_filter: str | None = None,
        session_tag: str | None = None,
        probe:       str | None = None,
    ) -> str:
        """Returns the path to the generated ZIP, or "" on failure / no data."""
        logger.info("Starting data export to ZIP...")

        data = self.db_service.get_all_filtered_measurements(
            name_filter=name_filter, start_date=start_date, end_date=end_date,
            shelf=shelf, book=book, page=page, note_filter=note_filter,
            session_tag=session_tag, probe=probe,
        )
        if not data:
            logger.info("No data found matching filters to export.")
            return ""

        export_dir = Path(export_dir)
        temp_dir   = Path(tempfile.mkdtemp())
        img_dir    = temp_dir / "img"
        csv_path   = temp_dir / "measurements.csv"

        try:
            img_dir.mkdir(parents=True, exist_ok=True)

            # Copy images preserving the stored filenames.
            for row in data:
                for db_key in ("RefImage", "MatImage"):
                    filename = row.get(db_key)
                    if not filename:
                        continue
                    src = self.image_dir_path / filename
                    if not src.exists():
                        logger.warning("Source image not found, skipping: %s", src)
                        continue
                    shutil.copy(src, img_dir / filename)
                # Rewrite the path fields to be ZIP-relative.
                if row.get("RefImage"):
                    row["RefImage"] = f"img/{row['RefImage']}"
                if row.get("MatImage"):
                    row["MatImage"] = f"img/{row['MatImage']}"

            export_headers = self._build_header()

            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=export_headers, extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(data)

            timestamp     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_base_path = export_dir / f"measurements_export_{timestamp}"
            zip_filepath  = shutil.make_archive(
                base_name=str(zip_base_path), format="zip", root_dir=str(temp_dir),
            )

            logger.info("Successfully exported %d rows to %s", len(data), zip_filepath)
            return zip_filepath

        except Exception as e:
            logger.exception("Unexpected error during export: %s", e)
            return ""
        finally:
            try:
                shutil.rmtree(temp_dir)
                logger.debug("Cleaned up temp directory: %s", temp_dir)
            except OSError as e:
                logger.warning("Error cleaning up temp directory %s: %s", temp_dir, e)

    # ------------------------------------------------------------------

    @staticmethod
    def _build_header() -> list[str]:
        """Preferred order first, anything else from VALID_COLUMNS after."""
        exportable = VALID_COLUMNS - {"id"}
        ordered: list[str] = []
        seen: set[str] = set()
        for col in _PREFERRED_ORDER:
            if col in exportable:
                ordered.append(col)
                seen.add(col)
        for col in sorted(exportable):
            if col not in seen:
                ordered.append(col)
        return ordered