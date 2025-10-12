import sqlite3
from typing import Dict, Any, List, Optional

class DatabaseService:
    """
    Manages all database operations for storing and retrieving measurements
    using an SQLite3 database.
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

    def get_measurements(self) -> List[Dict[str, Any]]:
        """
        Retrieves all measurement records from the database, ordered by date descending.
        """
        try:
            # --- THE FIX IS HERE ---
            # Add 'id DESC' as a secondary sort to handle records with the same timestamp.
            self.cursor.execute("SELECT * FROM measurements ORDER BY Date DESC, id DESC")
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error fetching measurements: {e}")
            return []

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
