import sqlite3
from typing import Dict, Any, List, Optional, Tuple

class DatabaseService:
    """
    Manages all database operations for storing and retrieving measurements using an SQLite3 database.
    """

    def __init__(self, db_path: str):
        """
        Initializes the database connection and creates the table if it doesn't exist.

        Args:
            db_path (str): The file path for the SQLite database.
        """
        try:
            self.db_path = db_path
            # Enable multi-threaded access
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            self._create_table()
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            raise

    def _create_table(self):
        """
        Creates the 'measurements' table if it is not already present.
        """
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
            # Check and add columns if they don't exist (for migration)
            self.cursor.execute("PRAGMA table_info(measurements)")
            columns = [col['name'] for col in self.cursor.fetchall()]
            
            if 'Wavelength' not in columns:
                print("Adding 'Wavelength' column to database...")
                self.cursor.execute("ALTER TABLE measurements ADD COLUMN Wavelength REAL")
            
            if 'Note' not in columns:
                print("Adding 'Note' column to database...")
                self.cursor.execute("ALTER TABLE measurements ADD COLUMN Note TEXT")

            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating/updating table: {e}")

    def save_measurement(self, data: Dict[str, Any]) -> int:
        """
        Saves a new measurement record to the database.
        Dynamically builds the query based on the keys in the data.
        - If 'Date' is in data, it's used.
        - If 'Date' is NOT in data, the DB's DEFAULT is used.
        """
        try:
            if not data:
                print("Error: No data provided to save_measurement.")
                return -1

            # Get column names and parameter placeholders from data keys
            columns = ", ".join(data.keys())
            placeholders = ", ".join(f":{key}" for key in data.keys())
            
            query = f"INSERT INTO measurements ({columns}) VALUES ({placeholders})"
            
            self.cursor.execute(query, data)
            self.conn.commit()
            return self.cursor.lastrowid
        
        except sqlite3.Error as e:
            print(f"Error saving measurement: {e}")
            print(f"Query: {query}")
            print(f"Data: {list(data.keys())}") # Don't log full data (images are huge)
            return -1

    def get_measurement(self, measurement_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single measurement record by its ID.
        """
        try:
            self.cursor.execute("SELECT * FROM measurements WHERE id = ?", (measurement_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Error fetching measurement with id {measurement_id}: {e}")
            return None

    def _build_filter_query(
        self,
        base_query: str,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        shelf: Optional[str] = None,
        book: Optional[str] = None,
        page: Optional[str] = None,
        note_filter: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Helper to build WHERE clauses for filtering."""
        query = base_query
        where_clauses = []
        params = {}

        if name_filter:
            where_clauses.append("Name LIKE :name")
            params["name"] = f"%{name_filter}%"
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
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        shelf: Optional[str] = None,
        book: Optional[str] = None,
        page: Optional[str] = None,
        note_filter: Optional[str] = None,
        page_num: int = 1,
        per_page: int = 20,
        order_by: Optional[str] = "Date",
        order_dir: Optional[str] = "DESC"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves a paginated and filtered list of measurement records.
        """
        query, params = self._build_filter_query(
            "SELECT * FROM measurements",
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )

        # Add ordering (with sanitation)
        valid_columns = ('id', 'Date', 'Name', 'Layer', 'Wavelength', 'Shelf', 'Book', 'Page', 'Note')
        safe_order_by = order_by if order_by in valid_columns else "Date"
        safe_order_dir = order_dir if order_dir in ('ASC', 'DESC') else "DESC"

        query += f" ORDER BY {safe_order_by} {safe_order_dir}"
        if safe_order_by != 'id':
            query += ", id DESC" # Add stable secondary sort

        # Add pagination
        offset = (page_num - 1) * per_page
        query += " LIMIT :limit OFFSET :offset"
        params["limit"] = per_page
        params["offset"] = offset

        try:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error fetching measurements: {e}")
            return []

    def get_all_filtered_measurements(
        self,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        shelf: Optional[str] = None,
        book: Optional[str] = None,
        page: Optional[str] = None,
        note_filter: Optional[str] = None,
        order_by: Optional[str] = "Date",
        order_dir: Optional[str] = "DESC"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves ALL filtered measurement records (no pagination).
        Used for CSV export.
        """
        query, params = self._build_filter_query(
            "SELECT * FROM measurements",
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )
        
        # Add ordering (with sanitation)
        valid_columns = ('id', 'Date', 'Name', 'Layer', 'Wavelength', 'Shelf', 'Book', 'Page', 'Note')
        safe_order_by = order_by if order_by in valid_columns else "Date"
        safe_order_dir = order_dir if order_dir in ('ASC', 'DESC') else "DESC"

        query += f" ORDER BY {safe_order_by} {safe_order_dir}"
        if safe_order_by != 'id':
            query += ", id DESC" # Add stable secondary sort

        try:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error fetching all filtered measurements: {e}")
            return []
    
    def get_measurements_count(
        self,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        shelf: Optional[str] = None,
        book: Optional[str] = None,
        page: Optional[str] = None,
        note_filter: Optional[str] = None
    ) -> int:
        """
        Gets the total count of measurements matching the filters.
        """
        query, params = self._build_filter_query(
            "SELECT COUNT(*) FROM measurements",
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )

        try:
            self.cursor.execute(query, params)
            count = self.cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            print(f"Error counting measurements: {e}")
            return 0

    def _get_unique_column_values(self, column_name: str) -> List[str]:
        """Helper to get unique, non-null, ordered values from a column."""
        try:
            self.cursor.execute(f"SELECT DISTINCT {column_name} FROM measurements WHERE {column_name} IS NOT NULL AND {column_name} != '' ORDER BY {column_name}")
            rows = self.cursor.fetchall()
            return [row[column_name] for row in rows]
        except sqlite3.Error as e:
            print(f"Error fetching unique {column_name} values: {e}")
            return []

    def get_unique_names(self) -> List[str]:
        """Retrieves a list of all unique names for filter suggestions."""
        return self._get_unique_column_values("Name")
    
    def get_unique_shelves(self) -> List[str]:
        """Retrieves a list of all unique shelves for filter suggestions."""
        return self._get_unique_column_values("Shelf")
        
    def get_unique_books(self) -> List[str]:
        """Retrieves a list of all unique books for filter suggestions."""
        return self._get_unique_column_values("Book")

    def get_unique_pages(self) -> List[str]:
        """Retrieves a list of all unique pages for filter suggestions."""
        return self._get_unique_column_values("Page")

    def get_unique_notes(self) -> List[str]:
        """Retrieves a list of all unique notes for filter suggestions."""
        return self._get_unique_column_values("Note")

    def delete_measurement(self, measurement_id: int) -> bool:
        """
        Deletes a measurement record from the database by its ID.
        """
        try:
            self.cursor.execute("DELETE FROM measurements WHERE id = ?", (measurement_id,))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error deleting measurement with id {measurement_id}: {e}")
            return False

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()