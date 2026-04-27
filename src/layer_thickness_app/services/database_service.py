from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VALID_COLUMNS = frozenset({
    "id", "Date", "Name", "Layer", "Wavelength",
    "RefImage", "MatImage", "Shelf", "Book", "Page", "Note",
    "Mode", "ThicknessCorrected",
    "ReferenceThickness", "SessionTag",
    "MeanGrayRef", "MeanGraySample",
    "StdGrayRef", "StdGraySample",
    "FrameCountRef", "FrameCountSample",
    "Probe", "RunIndex",
})

VALID_CAL_COLUMNS = frozenset({
    "id", "Date", "Name", "Shelf", "Book", "Page",
    "Wavelength", "Mode", "Slope", "Intercept", "RSquared",
    "NSamples", "MinRefNm", "MaxRefNm", "SessionTag",
    "IsActive", "Note",
})


class DatabaseService:
    """Persists measurements and calibration models in a local SQLite DB."""

    def __init__(self, db_path: str):
        try:
            self.db_path = db_path
            db_parent_dir = Path(self.db_path).parent
            db_parent_dir.mkdir(parents=True, exist_ok=True)

            self.image_dir_path = db_parent_dir / "images"
            self.image_dir_path.mkdir(parents=True, exist_ok=True)

            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            # WAL is faster but leaves -shm/-wal sidecar files around between
            # runs. DELETE journal mode keeps the working directory clean and
            # is plenty fast for the single-writer workload here.
            self.conn.execute("PRAGMA journal_mode=DELETE")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.cursor = self.conn.cursor()

            self._create_measurements_table()
            self._create_calibrations_table()
            self._create_indexes()
        except (sqlite3.Error, OSError) as e:
            logger.error("Database connection/setup error at %s: %s", db_path, e)
            raise

    # ==================================================================
    # Schema
    # ==================================================================

    def _create_measurements_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                Date               TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
                Name               TEXT,
                Layer              REAL NOT NULL,
                Wavelength         REAL,
                RefImage           TEXT NOT NULL,
                MatImage           TEXT NOT NULL,
                Shelf              TEXT NOT NULL,
                Book               TEXT NOT NULL,
                Page               TEXT NOT NULL,
                Note               TEXT,
                Mode               TEXT    DEFAULT 'single',
                ThicknessCorrected REAL,
                ReferenceThickness REAL,
                SessionTag         TEXT,
                MeanGrayRef        REAL,
                MeanGraySample     REAL,
                StdGrayRef         REAL,
                StdGraySample      REAL,
                FrameCountRef      INTEGER,
                FrameCountSample   INTEGER,
                Probe              TEXT,
                RunIndex           INTEGER
            )
        """)
        self.conn.commit()

    def _create_calibrations_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS calibrations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                Date        TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
                Name        TEXT,
                Shelf       TEXT NOT NULL,
                Book        TEXT NOT NULL,
                Page        TEXT NOT NULL,
                Wavelength  REAL NOT NULL,
                Mode        TEXT NOT NULL,
                Slope       REAL NOT NULL,
                Intercept   REAL NOT NULL,
                RSquared    REAL NOT NULL,
                NSamples    INTEGER NOT NULL,
                MinRefNm    REAL,
                MaxRefNm    REAL,
                SessionTag  TEXT,
                IsActive    INTEGER DEFAULT 0,
                Note        TEXT
            )
        """)
        self.conn.commit()

    def _create_indexes(self):
        indexes = [
            ("idx_meas_date",    "measurements(Date DESC)"),
            ("idx_meas_name",    "measurements(Name)"),
            ("idx_meas_shelf",   "measurements(Shelf)"),
            ("idx_meas_book",    "measurements(Book)"),
            ("idx_meas_page",    "measurements(Page)"),
            ("idx_meas_session", "measurements(SessionTag)"),
            ("idx_meas_mode",    "measurements(Mode)"),
            ("idx_meas_probe",   "measurements(Probe)"),
            ("idx_cal_material", "calibrations(Shelf, Book, Page, Wavelength, Mode)"),
            ("idx_cal_active",   "calibrations(IsActive)"),
            ("idx_cal_session",  "calibrations(SessionTag)"),
        ]
        try:
            for idx_name, idx_target in indexes:
                self.cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_target}"
                )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error("Error creating indexes: %s", e)

    # ==================================================================
    # Measurements - write
    # ==================================================================

    def save_measurement(self, data: dict[str, Any]) -> int:
        if not data:
            logger.error("No data provided to save_measurement.")
            return -1
        clean = {k: v for k, v in data.items()
                 if k in VALID_COLUMNS or k in ("RefImage", "MatImage")}
        try:
            columns      = ", ".join(clean.keys())
            placeholders = ", ".join(f":{k}" for k in clean.keys())
            self.cursor.execute(
                f"INSERT INTO measurements ({columns}) VALUES ({placeholders})",
                clean,
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            logger.error("Error saving measurement: %s", e)
            return -1

    def delete_measurement(self, measurement_id: int) -> bool:
        try:
            self.cursor.execute(
                "SELECT RefImage, MatImage FROM measurements WHERE id = ?",
                (measurement_id,),
            )
            row = self.cursor.fetchone()
            self.cursor.execute(
                "DELETE FROM measurements WHERE id = ?", (measurement_id,)
            )
            self.conn.commit()
            row_was_deleted = self.cursor.rowcount > 0
            if row and row_was_deleted:
                self._delete_image_file(row["RefImage"])
                self._delete_image_file(row["MatImage"])
            return row_was_deleted
        except sqlite3.Error as e:
            logger.error("Error deleting measurement %s: %s", measurement_id, e)
            return False

    # ==================================================================
    # Measurements - read (single)
    # ==================================================================

    def get_measurement(self, measurement_id: int) -> dict[str, Any] | None:
        try:
            self.cursor.execute(
                "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
            )
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("Error fetching measurement %s: %s", measurement_id, e)
            return None

    # ==================================================================
    # Measurements - read (filtered / paginated)
    # ==================================================================

    def _build_filter_query(
        self,
        base_query:  str,
        name_filter: str | None = None,
        start_date:  str | None = None,
        end_date:    str | None = None,
        shelf:       str | None = None,
        book:        str | None = None,
        page:        str | None = None,
        note_filter: str | None = None,
        session_tag: str | None = None,
        mode_filter: str | None = None,
        probe:       str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        where_clauses: list[str] = []
        params: dict[str, Any]  = {}
        if name_filter:
            where_clauses.append("Name = :name");              params["name"] = name_filter
        if start_date:
            where_clauses.append("DATE(Date) >= :start_date"); params["start_date"] = start_date
        if end_date:
            where_clauses.append("DATE(Date) <= :end_date");   params["end_date"] = end_date
        if shelf:
            where_clauses.append("Shelf = :shelf");            params["shelf"] = shelf
        if book:
            where_clauses.append("Book = :book");              params["book"] = book
        if page:
            where_clauses.append("Page = :page");              params["page"] = page
        if note_filter:
            where_clauses.append("Note LIKE :note");           params["note"] = f"%{note_filter}%"
        if session_tag:
            where_clauses.append("SessionTag = :session_tag"); params["session_tag"] = session_tag
        if mode_filter:
            where_clauses.append("Mode = :mode_filter");       params["mode_filter"] = mode_filter
        if probe:
            where_clauses.append("Probe = :probe");            params["probe"] = probe

        query = base_query
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        return query, params

    def get_measurements(
        self,
        name_filter: str | None = None, start_date: str | None = None,
        end_date:    str | None = None, shelf: str | None = None,
        book:        str | None = None, page: str | None = None,
        note_filter: str | None = None, session_tag: str | None = None,
        mode_filter: str | None = None, probe: str | None = None,
        page_num:    int = 1, per_page: int = 20,
        order_by:    str = "Date", order_dir: str = "DESC",
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Returns ``(rows, total_count)``. The total is computed via a
        window function in the same SELECT so the page only makes one
        round-trip.
        """
        safe_order_by  = order_by  if order_by  in VALID_COLUMNS else "Date"
        safe_order_dir = order_dir if order_dir in ("ASC", "DESC") else "DESC"
        base = "SELECT *, COUNT(*) OVER() AS __total FROM measurements"

        query, params = self._build_filter_query(
            base, name_filter, start_date, end_date, shelf, book, page,
            note_filter, session_tag, mode_filter, probe,
        )
        query += f" ORDER BY {safe_order_by} {safe_order_dir}"
        if safe_order_by != "id":
            query += ", id DESC"
        offset = (page_num - 1) * per_page
        query += " LIMIT :limit OFFSET :offset"
        params["limit"]  = per_page
        params["offset"] = offset

        try:
            self.cursor.execute(query, params)
            rows = [dict(r) for r in self.cursor.fetchall()]
            total = int(rows[0]["__total"]) if rows else 0
            for r in rows:
                r.pop("__total", None)
            if total == 0:
                # Empty page may still have data on earlier pages.
                total = self.get_measurements_count(
                    name_filter, start_date, end_date, shelf, book, page,
                    note_filter, session_tag, mode_filter, probe,
                )
            return rows, total
        except sqlite3.Error as e:
            logger.error("Error fetching measurements: %s", e)
            return [], 0

    def get_all_filtered_measurements(
        self,
        name_filter: str | None = None, start_date: str | None = None,
        end_date:    str | None = None, shelf: str | None = None,
        book:        str | None = None, page: str | None = None,
        note_filter: str | None = None, session_tag: str | None = None,
        mode_filter: str | None = None, probe: str | None = None,
        order_by:    str = "Date", order_dir: str = "DESC",
    ) -> list[dict[str, Any]]:
        query, params = self._build_filter_query(
            "SELECT * FROM measurements",
            name_filter, start_date, end_date, shelf, book, page,
            note_filter, session_tag, mode_filter, probe,
        )
        safe_order_by  = order_by  if order_by  in VALID_COLUMNS else "Date"
        safe_order_dir = order_dir if order_dir in ("ASC", "DESC") else "DESC"
        query += f" ORDER BY {safe_order_by} {safe_order_dir}"
        if safe_order_by != "id":
            query += ", id DESC"
        try:
            self.cursor.execute(query, params)
            return [dict(r) for r in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching all filtered measurements: %s", e)
            return []

    def get_measurements_count(
        self,
        name_filter: str | None = None, start_date: str | None = None,
        end_date:    str | None = None, shelf: str | None = None,
        book:        str | None = None, page: str | None = None,
        note_filter: str | None = None, session_tag: str | None = None,
        mode_filter: str | None = None, probe: str | None = None,
    ) -> int:
        query, params = self._build_filter_query(
            "SELECT COUNT(*) FROM measurements",
            name_filter, start_date, end_date, shelf, book, page,
            note_filter, session_tag, mode_filter, probe,
        )
        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error("Error counting measurements: %s", e)
            return 0

    # ==================================================================
    # Measurements - campaign queries
    # ==================================================================

    def get_calibration_rows(
        self,
        book:          str,
        page:          str,
        session_tag:   str | None = None,
        probe:         str | None = None,
        wavelength_um: float | None = None,
        mode:          str | None = None,
    ) -> list[dict[str, Any]]:
        """Rows with a known ReferenceThickness; the calibration pool."""
        query = """
            SELECT id, Layer, ThicknessCorrected, ReferenceThickness,
                   Mode, FrameCountRef, FrameCountSample,
                   SessionTag, Probe, RunIndex, Date, Wavelength, Shelf
            FROM measurements
            WHERE Book = :book
              AND Page = :page
              AND ReferenceThickness IS NOT NULL
        """
        params: dict[str, Any] = {"book": book, "page": page}
        if session_tag:
            query += " AND SessionTag = :session_tag"
            params["session_tag"] = session_tag
        if probe:
            query += " AND Probe = :probe"
            params["probe"] = probe
        if wavelength_um is not None:
            query += " AND (Wavelength IS NULL OR Wavelength = :wavelength)"
            params["wavelength"] = wavelength_um
        if mode:
            query += " AND (Mode IS NULL OR Mode = :mode)"
            params["mode"] = mode
        query += " ORDER BY ReferenceThickness ASC, Date ASC"
        try:
            self.cursor.execute(query, params)
            return [dict(r) for r in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching calibration rows: %s", e)
            return []

    def get_session_measurements(self, session_tag: str) -> list[dict[str, Any]]:
        try:
            self.cursor.execute(
                "SELECT * FROM measurements WHERE SessionTag = ? ORDER BY Date ASC",
                (session_tag,),
            )
            return [dict(r) for r in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching session '%s': %s", session_tag, e)
            return []

    def get_msa_rows(
        self,
        book:          str,
        page:          str,
        reference_nm:  float,
        session_tag:   str | None = None,
        probe:         str | None = None,
        wavelength_um: float | None = None,
        mode:          str | None = None,
        tolerance:     float = 0.5,
    ) -> list[dict[str, Any]]:
        """Repeated-measurement series for a single reference sample."""
        query = """
            SELECT id, Layer, ThicknessCorrected, ReferenceThickness,
                   Mode, FrameCountRef, FrameCountSample, Wavelength,
                   SessionTag, Probe, RunIndex, Date, Shelf
            FROM measurements
            WHERE Book = :book
              AND Page = :page
              AND ReferenceThickness BETWEEN :ref_lo AND :ref_hi
        """
        params: dict[str, Any] = {
            "book": book, "page": page,
            "ref_lo": reference_nm - tolerance,
            "ref_hi": reference_nm + tolerance,
        }
        if session_tag:
            query += " AND SessionTag = :session_tag"
            params["session_tag"] = session_tag
        if probe:
            query += " AND Probe = :probe"
            params["probe"] = probe
        if wavelength_um is not None:
            query += " AND (Wavelength IS NULL OR Wavelength = :wavelength)"
            params["wavelength"] = wavelength_um
        if mode:
            query += " AND (Mode IS NULL OR Mode = :mode)"
            params["mode"] = mode
        query += " ORDER BY Date ASC"
        try:
            self.cursor.execute(query, params)
            return [dict(r) for r in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching MSA rows: %s", e)
            return []

    # ==================================================================
    # Calibrations - write / read / activate
    # ==================================================================

    def save_calibration(self, data: dict[str, Any]) -> int:
        if not data:
            logger.error("No data provided to save_calibration.")
            return -1
        clean = {k: v for k, v in data.items() if k in VALID_CAL_COLUMNS}
        try:
            columns      = ", ".join(clean.keys())
            placeholders = ", ".join(f":{k}" for k in clean.keys())
            self.cursor.execute(
                f"INSERT INTO calibrations ({columns}) VALUES ({placeholders})",
                clean,
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            logger.error("Error saving calibration: %s", e)
            return -1

    def get_calibration(self, calibration_id: int) -> dict[str, Any] | None:
        try:
            self.cursor.execute(
                "SELECT * FROM calibrations WHERE id = ?", (calibration_id,)
            )
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("Error fetching calibration %s: %s", calibration_id, e)
            return None

    def get_calibrations(
        self,
        shelf:       str | None = None, book: str | None = None,
        page:        str | None = None, wavelength: float | None = None,
        mode:        str | None = None, session_tag: str | None = None,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        params: dict[str, Any]  = {}
        if shelf:       where_clauses.append("Shelf = :shelf");            params["shelf"] = shelf
        if book:        where_clauses.append("Book = :book");              params["book"] = book
        if page:        where_clauses.append("Page = :page");              params["page"] = page
        if wavelength is not None:
            where_clauses.append("Wavelength = :wavelength");              params["wavelength"] = wavelength
        if mode:        where_clauses.append("Mode = :mode");              params["mode"] = mode
        if session_tag: where_clauses.append("SessionTag = :session_tag"); params["session_tag"] = session_tag
        if active_only: where_clauses.append("IsActive = 1")

        query = "SELECT * FROM calibrations"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY Date DESC, id DESC"

        try:
            self.cursor.execute(query, params)
            return [dict(r) for r in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching calibrations: %s", e)
            return []

    def delete_calibration(self, calibration_id: int) -> bool:
        try:
            self.cursor.execute(
                "DELETE FROM calibrations WHERE id = ?", (calibration_id,)
            )
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error("Error deleting calibration %s: %s", calibration_id, e)
            return False

    def get_active_calibration(
        self, shelf: str, book: str, page: str,
        wavelength_um: float, mode: str,
    ) -> dict[str, Any] | None:
        try:
            self.cursor.execute(
                """
                SELECT * FROM calibrations
                 WHERE Shelf=? AND Book=? AND Page=?
                   AND Wavelength=? AND Mode=? AND IsActive=1
                 LIMIT 1
                """,
                (shelf, book, page, wavelength_um, mode),
            )
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("Error fetching active calibration: %s", e)
            return None

    def set_active_calibration(self, calibration_id: int) -> bool:
        """
        Atomically deactivates any other calibration sharing the same
        (Shelf, Book, Page, Wavelength, Mode) tuple, then marks the given
        row active.
        """
        try:
            self.cursor.execute(
                "SELECT Shelf, Book, Page, Wavelength, Mode "
                "FROM calibrations WHERE id = ?", (calibration_id,),
            )
            row = self.cursor.fetchone()
            if not row:
                logger.warning("set_active_calibration: id %s not found", calibration_id)
                return False

            self.cursor.execute("BEGIN")
            self.cursor.execute(
                """
                UPDATE calibrations SET IsActive = 0
                 WHERE Shelf=? AND Book=? AND Page=?
                   AND Wavelength=? AND Mode=?
                """,
                (row["Shelf"], row["Book"], row["Page"],
                 row["Wavelength"], row["Mode"]),
            )
            self.cursor.execute(
                "UPDATE calibrations SET IsActive = 1 WHERE id = ?",
                (calibration_id,),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error("Error setting active calibration %s: %s", calibration_id, e)
            self.conn.rollback()
            return False

    def deactivate_calibration(self, calibration_id: int) -> bool:
        try:
            self.cursor.execute(
                "UPDATE calibrations SET IsActive = 0 WHERE id = ?",
                (calibration_id,),
            )
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error("Error deactivating calibration %s: %s", calibration_id, e)
            return False

    # ==================================================================
    # Unique-value helpers (filter ComboBoxes)
    # ==================================================================

    def _get_unique_column_values(self, column_name: str) -> list[str]:
        if not column_name.replace("_", "").isalnum():
            logger.warning("Invalid column name requested: %s", column_name)
            return []
        try:
            self.cursor.execute(
                f"SELECT DISTINCT {column_name} FROM measurements "
                f"WHERE {column_name} IS NOT NULL AND {column_name} != '' "
                f"ORDER BY {column_name}"
            )
            return [row[column_name] for row in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching unique %s values: %s", column_name, e)
            return []

    def get_unique_names(self)    -> list[str]: return self._get_unique_column_values("Name")
    def get_unique_shelves(self)  -> list[str]: return self._get_unique_column_values("Shelf")
    def get_unique_books(self)    -> list[str]: return self._get_unique_column_values("Book")
    def get_unique_pages(self)    -> list[str]: return self._get_unique_column_values("Page")
    def get_unique_notes(self)    -> list[str]: return self._get_unique_column_values("Note")
    def get_unique_sessions(self) -> list[str]: return self._get_unique_column_values("SessionTag")
    def get_unique_probes(self)   -> list[str]: return self._get_unique_column_values("Probe")

    def get_pages_for_book(self, book: str) -> list[str]:
        """Distinct Page values seen in measurements for a given Book."""
        if not book:
            return []
        try:
            self.cursor.execute(
                "SELECT DISTINCT Page FROM measurements "
                "WHERE Book = ? AND Page IS NOT NULL AND Page != '' "
                "ORDER BY Page",
                (book,),
            )
            return [row["Page"] for row in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Error fetching pages for book %s: %s", book, e)
            return []

    def get_shelf_for_book_page(self, book: str, page: str) -> str | None:
        """Looks up the shelf for a (Book, Page) pair from any matching row."""
        if not book or not page:
            return None
        try:
            self.cursor.execute(
                "SELECT Shelf FROM measurements "
                "WHERE Book = ? AND Page = ? AND Shelf IS NOT NULL AND Shelf != '' "
                "LIMIT 1",
                (book, page),
            )
            row = self.cursor.fetchone()
            return row["Shelf"] if row else None
        except sqlite3.Error as e:
            logger.error("Error fetching shelf for %s/%s: %s", book, page, e)
            return None

    # ==================================================================
    # Housekeeping
    # ==================================================================

    def _delete_image_file(self, filename: str | None):
        if not filename:
            return
        try:
            file_path = self.image_dir_path / filename
            if file_path.exists():
                file_path.unlink()
                logger.info("Deleted image file: %s", file_path)
            else:
                logger.warning("Tried to delete file, but not found: %s", file_path)
        except OSError as e:
            logger.error("Error deleting image file %s: %s", filename, e)

    def close(self):
        if self.conn:
            try:
                # Force a checkpoint so any leftover -wal data is folded back
                # into the main DB file. After TRUNCATE both -wal and -shm
                # are size-zero (or removed entirely on next open in DELETE
                # journal mode).
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.conn.commit()
            except sqlite3.Error as e:
                logger.debug("WAL checkpoint on close failed: %s", e)
            try:
                self.conn.close()
            except sqlite3.Error as e:
                logger.debug("Error closing DB connection: %s", e)
            self.conn = None
            self._cleanup_sidecar_files()

    def _cleanup_sidecar_files(self) -> None:
        """Remove -wal and -shm files left over from a previous WAL session."""
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.db_path}{suffix}")
            if sidecar.exists():
                try:
                    sidecar.unlink()
                    logger.info("Removed leftover SQLite sidecar: %s", sidecar)
                except OSError as e:
                    logger.debug("Could not remove %s: %s", sidecar, e)