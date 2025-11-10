import pytest
import sqlite3
from pathlib import Path
from typing import Dict, Any, Generator

from layer_thickness_app.services.database_service import DatabaseService

# ----------------------------------------------------------------------


# --- Sample Data ---

# A full record with all fields
SAMPLE_DATA_1: Dict[str, Any] = {
    "Date": "2025-10-28 10:00:00",
    "Name": "Silicon Wafer Test",
    "Layer": 150.7,
    "Wavelength": 633.0,
    "RefImage": "path/to/ref1.png",
    "MatImage": "path/to/mat1.png",
    "Shelf": "A1",
    "Book": "Si",
    "Page": "Johnson",
    "Note": "Test run 1"
}

# A second record with different values for filtering
SAMPLE_DATA_2: Dict[str, Any] = {
    "Date": "2025-10-29 11:00:00",
    "Name": "PMMA Sample",
    "Layer": 210.2,
    "Wavelength": 405.5,
    "RefImage": "path/to/ref2.png",
    "MatImage": "path/to/mat2.png",
    "Shelf": "B2",
    "Book": "PMMA",
    "Page": "Smith",
    "Note": "Calibration sample"
}

# A third record for testing partial filters and date ranges
SAMPLE_DATA_3: Dict[str, Any] = {
    "Date": "2025-10-30 12:00:00",
    "Name": "Silicon Wafer Test",  # Duplicate name
    "Layer": 155.0,
    "Wavelength": 633.0,
    "RefImage": "path/to/ref3.png",
    "MatImage": "path/to/mat3.png",
    "Shelf": "A1",  # Duplicate shelf
    "Book": "Si",
    "Page": "Johnson",
    "Note": "Test run 2"
}

# A record with minimal required fields (Wavelength/Note/Name are optional)
SAMPLE_DATA_4: Dict[str, Any] = {
    "Date": "2025-10-30 13:00:00",
    "Name": None,  # Test None
    "Layer": 99.0,
    "RefImage": "path/to/ref4.png",
    "MatImage": "path/to/mat4.png",
    "Shelf": "C3",
    "Book": "Archive",
    "Page": "Old"
    # No Note, No Wavelength
}


# --- Pytest Fixtures ---

@pytest.fixture
def db_service(tmp_path: Path) -> Generator[DatabaseService, None, None]:
    """
    Pytest fixture to create a new DatabaseService instance for each test
    using a temporary, isolated database file.
    """
    db_path = tmp_path / "test.db"
    service = DatabaseService(str(db_path))

    # Yield the service to the test
    yield service

    # Teardown: close the connection
    service.close()
    # tmp_path automatically handles file/directory deletion


@pytest.fixture
def populated_db_service(db_service: DatabaseService) -> DatabaseService:
    """
    Fixture that depends on 'db_service' and populates it with
    the sample data.
    """
    db_service.save_measurement(SAMPLE_DATA_1)
    db_service.save_measurement(SAMPLE_DATA_2)
    db_service.save_measurement(SAMPLE_DATA_3)
    db_service.save_measurement(SAMPLE_DATA_4)
    return db_service


# --- Test Functions ---

def test_init_creates_directory(tmp_path: Path):
    """
    Test that the DatabaseService __init__ successfully creates the
    parent directory if it doesn't exist.
    """
    deep_db_path = tmp_path / "new_data_folder" / "measurements.db"

    # Ensure directory does NOT exist
    assert not deep_db_path.parent.exists()

    # Initialize the service
    service = DatabaseService(str(deep_db_path))

    # Check that the directory was created
    assert deep_db_path.parent.exists()
    assert deep_db_path.parent.is_dir()

    service.close()


def test_init_creates_table(db_service: DatabaseService):
    """
    Test if the 'measurements' table is created upon class initialization.
    """
    # Manually check the database schema
    cursor = db_service.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='measurements'")
    assert cursor.fetchone() is not None, "Table 'measurements' was not created."


def test_migration_adds_columns(tmp_path: Path):
    """
    Test that the _create_table migration logic successfully adds
    'Wavelength' and 'Note' columns to a pre-existing "old" database.
    """
    db_path = str(tmp_path / "old.db")

    # 1. Manually create an "old" database WITHOUT the new columns
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE measurements (
            id INTEGER PRIMARY KEY,
            Date TIMESTAMP,
            Name TEXT,
            Layer REAL NOT NULL,
            RefImage TEXT NOT NULL,
            MatImage TEXT NOT NULL,
            Shelf TEXT NOT NULL,
            Book TEXT NOT NULL,
            Page TEXT NOT NULL
        )
    """)
    conn.commit()

    # Check that the columns don't exist
    cursor.execute("PRAGMA table_info(measurements)")
    columns = [col[1] for col in cursor.fetchall()]
    assert 'Wavelength' not in columns
    assert 'Note' not in columns

    conn.close()

    # 2. Initialize DatabaseService on the *same file*.
    # This should trigger the migration logic in _create_table.
    service = DatabaseService(db_path)

    # 3. Check if the columns were added
    service.cursor.execute("PRAGMA table_info(measurements)")
    new_columns = [col['name'] for col in service.cursor.fetchall()]

    assert 'Wavelength' in new_columns
    assert 'Note' in new_columns

    service.close()


def test_save_and_get_measurement(db_service: DatabaseService):
    """
    Test saving a full measurement and retrieving it.
    """
    new_id = db_service.save_measurement(SAMPLE_DATA_1)
    assert isinstance(new_id, int)
    assert new_id > 0

    retrieved = db_service.get_measurement(new_id)
    assert retrieved is not None

    # Check that all saved data matches the retrieved data
    for key, value in SAMPLE_DATA_1.items():
        assert retrieved[key] == value

    # Check auto-generated fields
    assert retrieved['id'] == new_id


def test_save_measurement_default_date(db_service: DatabaseService):
    """
    Test that a measurement saved without a 'Date' key
    gets a default timestamp from the database.
    """
    data = SAMPLE_DATA_1.copy()
    del data["Date"]  # Remove date to test default

    new_id = db_service.save_measurement(data)
    retrieved = db_service.get_measurement(new_id)

    assert retrieved is not None
    assert retrieved['Date'] is not None
    assert isinstance(retrieved['Date'], str)
    assert len(retrieved['Date']) > 0  # e.g., '2025-10-28 10:00:00'


def test_get_measurement_not_found(db_service: DatabaseService):
    """
    Test that get_measurement returns None for a non-existent ID.
    """
    retrieved = db_service.get_measurement(9999)
    assert retrieved is None


def test_delete_measurement(db_service: DatabaseService):
    """
    Test deleting a measurement by its ID.
    """
    new_id = db_service.save_measurement(SAMPLE_DATA_1)

    # Verify it exists
    assert db_service.get_measurement(new_id) is not None

    # Delete it
    was_deleted = db_service.delete_measurement(new_id)
    assert was_deleted is True

    # Verify it's gone
    assert db_service.get_measurement(new_id) is None


def test_delete_measurement_not_found(db_service: DatabaseService):
    """
    Test that deleting a non-existent measurement returns False.
    """
    was_deleted = db_service.delete_measurement(9999)
    assert was_deleted is False


# --- Tests on Populated Database ---

def test_get_measurements_count(populated_db_service: DatabaseService):
    """
    Test the get_measurements_count method with various filters.
    """
    # Total count (4 samples added)
    assert populated_db_service.get_measurements_count() == 4

    # Filter by name (LIKE)
    count_si = populated_db_service.get_measurements_count(name_filter="Silicon")
    assert count_si == 2

    # Filter by shelf (Exact)
    count_a1 = populated_db_service.get_measurements_count(shelf="A1")
    assert count_a1 == 2

    # Filter by date range
    count_date = populated_db_service.get_measurements_count(
        start_date="2025-10-29",
        end_date="2025-10-30"
    )
    assert count_date == 3  # 29th (1), 30th (2)

    # Filter by note (LIKE)
    count_note = populated_db_service.get_measurements_count(note_filter="Test run")
    assert count_note == 2

    # Combined filters
    count_combo = populated_db_service.get_measurements_count(
        name_filter="Silicon",
        shelf="A1",
        start_date="2025-10-30"
    )
    assert count_combo == 1  # Only SAMPLE_DATA_3


def test_get_measurements_pagination(populated_db_service: DatabaseService):
    """
    Test the pagination logic of get_measurements.
    """
    # Get 4 records total, 2 per page
    page_1 = populated_db_service.get_measurements(per_page=2, page_num=1)
    assert len(page_1) == 2

    page_2 = populated_db_service.get_measurements(per_page=2, page_num=2)
    assert len(page_2) == 2

    page_3 = populated_db_service.get_measurements(per_page=2, page_num=3)
    assert len(page_3) == 0  # No more records

    # Check default order (Date DESC)
    assert page_1[0]['id'] == 4  # SAMPLE_DATA_4 (latest)
    assert page_1[1]['id'] == 3  # SAMPLE_DATA_3
    assert page_2[0]['id'] == 2  # SAMPLE_DATA_2
    assert page_2[1]['id'] == 1  # SAMPLE_DATA_1 (earliest)


def test_get_measurements_ordering(populated_db_service: DatabaseService):
    """
    Test the ordering logic of get_measurements.
    """
    # Order by Name, ASC. Nones (SAMPLE_DATA_4) are usually first in SQLite.
    results = populated_db_service.get_measurements(order_by="Name", order_dir="ASC")

    assert len(results) == 4
    assert results[0]['id'] == 4  # Name is None
    assert results[1]['id'] == 2  # Name is 'PMMA Sample'
    assert results[2]['id'] == 3  # Name is 'Silicon Wafer Test'
    assert results[3]['id'] == 1  # Name is 'Silicon Wafer Test' (stable sort by id DESC)

    # Order by Layer, DESC
    results_layer = populated_db_service.get_measurements(order_by="Layer", order_dir="DESC")
    assert results_layer[0]['id'] == 2  # Layer 210.2
    assert results_layer[1]['id'] == 3  # Layer 155.0
    assert results_layer[2]['id'] == 1  # Layer 150.7
    assert results_layer[3]['id'] == 4  # Layer 99.0


def test_get_all_filtered_measurements(populated_db_service: DatabaseService):
    """
    Test that get_all_filtered_measurements ignores pagination but
    respects filters.
    """
    results = populated_db_service.get_all_filtered_measurements(
        name_filter="Silicon"  # Should find 2
    )

    assert len(results) == 2
    assert results[0]['id'] == 3  # Default order Date DESC
    assert results[1]['id'] == 1


def test_get_unique_values(populated_db_service: DatabaseService):
    """
    Test the get_unique_... helper methods.
    """
    # 4 samples: A1, B2, A1, C3
    shelves = populated_db_service.get_unique_shelves()
    assert shelves == ["A1", "B2", "C3"]  # Should be unique and ordered

    # 4 samples: Si, PMMA, Si, Archive
    books = populated_db_service.get_unique_books()
    assert books == ["Archive", "PMMA", "Si"]

    # 4 samples: 'Silicon...', 'PMMA...', 'Silicon...', None
    names = populated_db_service.get_unique_names()
    assert names == ["PMMA Sample", "Silicon Wafer Test"]  # Nones are excluded