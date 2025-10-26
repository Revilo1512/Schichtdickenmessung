import sqlite3
from typing import Dict, Any, List, Optional

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
            self.conn = sqlite3.connect(db_path)
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
                    RefImage TEXT NOT NULL,
                    MatImage TEXT NOT NULL,
                    Shelf TEXT NOT NULL,
                    Book TEXT NOT NULL,
                    Page TEXT NOT NULL
                )
            """)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating table: {e}")

    def save_measurement(self, data: Dict[str, Any]) -> int:
        """
        Saves a new measurement record to the database.
        """
        query = """
            INSERT INTO measurements (Name, Layer, RefImage, MatImage, Shelf, Book, Page)
            VALUES (:Name, :Layer, :RefImage, :MatImage, :Shelf, :Book, :Page)
        """
        try:
            self.cursor.execute(query, data)
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Error saving measurement: {e}")
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
        
    def get_measurements(
        self,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieves a paginated and filtered list of measurement records.
        """
        query = "SELECT * FROM measurements"
        where_clauses = []
        params = {}

        if name_filter:
            where_clauses.append("Name LIKE :name")
            params["name"] = f"%{name_filter}%"

        if start_date:
            # Use DATE() function to compare just the date part
            where_clauses.append("DATE(Date) >= :start_date")
            params["start_date"] = start_date

        if end_date:
            where_clauses.append("DATE(Date) <= :end_date")
            params["end_date"] = end_date

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        # Add ordering
        query += " ORDER BY Date DESC, id DESC"

        # Add pagination
        offset = (page - 1) * per_page
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
    
    def get_measurements_count(
        self,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> int:
        """
        Gets the total count of measurements matching the filters.
        """
        query = "SELECT COUNT(*) FROM measurements"
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

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        try:
            self.cursor.execute(query, params)
            count = self.cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            print(f"Error counting measurements: {e}")
            return 0

    def get_unique_names(self) -> List[str]:
        """
        Retrieves a list of all unique names for filter suggestions.
        """
        try:
            self.cursor.execute("SELECT DISTINCT Name FROM measurements WHERE Name IS NOT NULL ORDER BY Name")
            rows = self.cursor.fetchall()
            return [row["Name"] for row in rows]
        except sqlite3.Error as e:
            print(f"Error fetching unique names: {e}")
            return []

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

