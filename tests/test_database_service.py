import unittest
import os
import sqlite3
from typing import Dict, Any

# Assuming the database_service.py is in a sibling directory or the path is configured.
# For this example, we'll assume it's accessible.
from layer_thickness_app.services.database_service import DatabaseService

class TestDatabaseService(unittest.TestCase):
    """
    Unit tests for the DatabaseService class.
    A separate, temporary database is created for each test function.
    """

    def setUp(self):
        """
        Set up a temporary database and a DatabaseService instance before each test.
        """
        self.db_path = "test_measurements.db"
        self.db_service = DatabaseService(self.db_path)
        
        # Sample data for reuse in tests
        self.sample_data_1: Dict[str, Any] = {
            "Name": "Silicon Wafer Test",
            "Layer": 150.7,
            "RefImage": "path/to/ref1.png",
            "MatImage": "path/to/mat1.png",
            "Shelf": "main",
            "Book": "Si",
            "Page": "Johnson"
        }
        self.sample_data_2: Dict[str, Any] = {
            "Name": None, # Test optional name
            "Layer": 210.2,
            "RefImage": "path/to/ref2.png",
            "MatImage": "path/to/mat2.png",
            "Shelf": "organics",
            "Book": "PMMA",
            "Page": "Smith"
        }

    def tearDown(self):
        """
        Close the database connection and remove the temporary database file after each test.
        """
        self.db_service.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_initialization_creates_table(self):
        """
        Test if the 'measurements' table is created upon class initialization.
        """
        # The setUp method already initializes the service.
        # We check if the table exists by querying it.
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'")
            self.assertIsNotNone(cursor.fetchone(), "Table 'measurements' should exist after initialization.")
        finally:
            conn.close()

    def test_save_measurement(self):
        """
        Test saving a measurement and verifying its contents.
        """
        new_id = self.db_service.save_measurement(self.sample_data_1)
        self.assertIsInstance(new_id, int)
        self.assertGreater(new_id, 0)

        retrieved_measurement = self.db_service.get_measurement(new_id)
        self.assertIsNotNone(retrieved_measurement)
        # Compare saved data with retrieved data (excluding auto-generated fields)
        for key in self.sample_data_1:
            self.assertEqual(retrieved_measurement[key], self.sample_data_1[key])

    def test_get_measurement_not_found(self):
        """
        Test that get_measurement returns None for a non-existent ID.
        """
        retrieved_measurement = self.db_service.get_measurement(999)
        self.assertIsNone(retrieved_measurement)

    def test_get_measurements(self):
        """
        Test retrieving all measurements, ensuring correct count and order.
        """
        # Initially, there should be no measurements
        self.assertEqual(len(self.db_service.get_measurements()), 0)

        # Add two measurements
        id1 = self.db_service.save_measurement(self.sample_data_1)
        id2 = self.db_service.save_measurement(self.sample_data_2)
        
        all_measurements = self.db_service.get_measurements()
        self.assertEqual(len(all_measurements), 2)
        
        # Check for descending order by date (which means the last one inserted is first)
        self.assertEqual(all_measurements[0]['id'], id2)
        self.assertEqual(all_measurements[1]['id'], id1)

    def test_delete_measurement(self):
        """
        Test deleting a measurement by its ID.
        """
        new_id = self.db_service.save_measurement(self.sample_data_1)
        
        # Verify it exists before deletion
        self.assertIsNotNone(self.db_service.get_measurement(new_id))

        # Perform deletion
        was_deleted = self.db_service.delete_measurement(new_id)
        self.assertTrue(was_deleted)

        # Verify it no longer exists
        self.assertIsNone(self.db_service.get_measurement(new_id))

    def test_delete_measurement_not_found(self):
        """
        Test that deleting a non-existent measurement returns False.
        """
        was_deleted = self.db_service.delete_measurement(999)
        self.assertFalse(was_deleted)

if __name__ == '__main__':
    # This allows the test to be run from the command line
    unittest.main()
