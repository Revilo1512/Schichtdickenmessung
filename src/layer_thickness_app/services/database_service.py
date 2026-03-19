import sqlite3
import os
import logging
from typing import Any
from pathlib import Path

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Manages all database operations for storing and retrieving measurements using an SQLite3 database.
    """

    def __init__(self, db_path: str):
        try:
            self.db_path = db_path
            db_parent_dir = Path(self.db_path).parent
            db_parent_dir.mkdir(parents=True, exist_ok=True)

            self.image_dir_path = db_parent_dir / "images"
            self.image_dir_path.mkdir(parents=True, exist_ok=True)

            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            self._create_table()
        except (sqlite3.Error, OSError) as e: 
            logger.error("Database connection/setup error at %s: %s", db_path, e)
            raise

    def _create_table(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Date TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
                    Name TEXT,
                    Layer REAL NOT NULL,
                    Wavelength REAL,
                    RefImage TEXT NOT NULL,
                    MatImage TEXT NOT NULL,
                    Shelf TEXT NOT NULL,
                    Book TEXT NOT NULL,
                    Page TEXT NOT NULL,
                    Note TEXT
                )
            """)
            
            self.cursor.execute("PRAGMA table_info(measurements)")
            columns = [col['name'] for col in self.cursor.fetchall()]
            
            if 'Wavelength' not in columns:
                logger.info("Adding 'Wavelength' column to database...")
                self.cursor.execute("ALTER TABLE measurements ADD COLUMN Wavelength REAL")
            
            if 'Note' not in columns:
                logger.info("Adding 'Note' column to database...")
                self.cursor.execute("ALTER TABLE measurements ADD COLUMN Note TEXT")

            self.conn.commit()
        except sqlite3.Error as e:
            logger.error("Error creating/updating table: %s", e)

    def save_measurement(self, data: dict[str, Any]) -> int:
        try:
            if not data:
                logger.error("No data provided to save_measurement.")
                return -1

            columns = ", ".join(data.keys())
            placeholders = ", ".join(f":{key}" for key in data.keys())
            
            query = f"INSERT INTO measurements ({columns}) VALUES ({placeholders})"
            
            self.cursor.execute(query, data)
            self.conn.commit()
            return self.cursor.lastrowid
        
        except sqlite3.Error as e:
            logger.error("Error saving measurement: %s", e)
            logger.debug("Data keys: %s", list(data.keys()))
            return -1

    def get_measurement(self, measurement_id: int) -> dict[str, Any] | None:
        try:
            self.cursor.execute("SELECT * FROM measurements WHERE id = ?", (measurement_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("Error fetching measurement with id %s: %s", measurement_id, e)
            return None

    def _build_filter_query(
        self,
        base_query: str,
        name_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        shelf: str | None = None,
        book: str | None = None,
        page: str | None = None,
        note_filter: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        
        query = base_query
        where_clauses = []
        params = {}

        if name_filter:
            where_clauses.append("Name = :name")
            params["name"] = name_filter
        if start_date:
            where_clauses.append("DATE(Date) >= :start_date")
            params["start_date"] = start_date
        if end_date:
            where_clauses.append("DATE(Date) <= :end_date")
            params["end_date"] = end_date
        if shelf:
            where_clauses.append("Shelf = :shelf")
            params["shelf"] = shelf
        if book:
            where_clauses.append("Book = :book")
            params["book"] = book
        if page:
            where_clauses.append("Page = :page")
            params["page"] = page
        if note_filter:
            where_clauses.append("Note LIKE :note")
            params["note"] = f"%{note_filter}%"

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        return query, params
        
    def get_measurements(
        self,
        name_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        shelf: str | None = None,
        book: str | None = None,
        page: str | None = None,
        note_filter: str | None = None,
        page_num: int = 1,
        per_page: int = 20,
        order_by: str = "Date",
        order_dir: str = "DESC"
    ) -> list[dict[str, Any]]:
        
        query, params = self._build_filter_query(
            "SELECT * FROM measurements",
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )

        valid_columns = ('id', 'Date', 'Name', 'Layer', 'Wavelength', 'Shelf', 'Book', 'Page', 'Note')
        safe_order_by = order_by if order_by in valid_columns else "Date"
        safe_order_dir = order_dir if order_dir in ('ASC', 'DESC') else "DESC"

        query += f" ORDER BY {safe_order_by} {safe_order_dir}"
        if safe_order_by != 'id':
            query += ", id DESC"

        offset = (page_num - 1) * per_page
        query += " LIMIT :limit OFFSET :offset"
        params["limit"] = per_page
        params["offset"] = offset

        try:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error("Error fetching measurements: %s", e)
            return []

    def get_all_filtered_measurements(
        self,
        name_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        shelf: str | None = None,
        book: str | None = None,
        page: str | None = None,
        note_filter: str | None = None,
        order_by: str = "Date",
        order_dir: str = "DESC"
    ) -> list[dict[str, Any]]:
        
        query, params = self._build_filter_query(
            "SELECT * FROM measurements",
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )
        
        valid_columns = ('id', 'Date', 'Name', 'Layer', 'Wavelength', 'Shelf', 'Book', 'Page', 'Note')
        safe_order_by = order_by if order_by in valid_columns else "Date"
        safe_order_dir = order_dir if order_dir in ('ASC', 'DESC') else "DESC"

        query += f" ORDER BY {safe_order_by} {safe_order_dir}"
        if safe_order_by != 'id':
            query += ", id DESC"

        try:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error("Error fetching all filtered measurements: %s", e)
            return []
    
    def get_measurements_count(
        self,
        name_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        shelf: str | None = None,
        book: str | None = None,
        page: str | None = None,
        note_filter: str | None = None
    ) -> int:
        
        query, params = self._build_filter_query(
            "SELECT COUNT(*) FROM measurements",
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )

        try:
            self.cursor.execute(query, params)
            return self.cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error("Error counting measurements: %s", e)
            return 0

    def _get_unique_column_values(self, column_name: str) -> list[str]:
        if not column_name.isalnum():
             logger.warning("Invalid column name requested: %s", column_name)
             return []
        try:
            self.cursor.execute(f"SELECT DISTINCT {column_name} FROM measurements WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name}")
            rows = self.cursor.fetchall()
            return [row[column_name] for row in rows]
        except sqlite3.Error as e:
            logger.error("Error fetching unique %s values: %s", column_name, e)
            return []

    def get_unique_names(self) -> list[str]:
        return self._get_unique_column_values("Name")
    
    def get_unique_shelves(self) -> list[str]:
        return self._get_unique_column_values("Shelf")
        
    def get_unique_books(self) -> list[str]:
        return self._get_unique_column_values("Book")

    def get_unique_pages(self) -> list[str]:
        return self._get_unique_column_values("Page")

    def get_unique_notes(self) -> list[str]:
        return self._get_unique_column_values("Note")

    def delete_measurement(self, measurement_id: int) -> bool:
        try:
            self.cursor.execute("SELECT RefImage, MatImage FROM measurements WHERE id = ?", (measurement_id,))
            row = self.cursor.fetchone()
            
            self.cursor.execute("DELETE FROM measurements WHERE id = ?", (measurement_id,))
            self.conn.commit()
            
            row_was_deleted = self.cursor.rowcount > 0
            
            if row and row_was_deleted:
                self._delete_image_file(row['RefImage'])
                self._delete_image_file(row['MatImage'])
                
            return row_was_deleted
        except sqlite3.Error as e:
            logger.error("Error deleting measurement with id %s: %s", measurement_id, e)
            return False

    def _delete_image_file(self, filename: str | None):
        if not filename:
            return
        try:
            file_path = self.image_dir_path / filename
            if file_path.exists():
                os.remove(file_path)
                logger.info("Deleted image file: %s", file_path)
            else:
                logger.warning("Tried to delete file, but it was not found: %s", file_path)
        except OSError as e:
            logger.error("Error deleting image file %s: %s", filename, e)

    def close(self):
        if self.conn:
            self.conn.close()