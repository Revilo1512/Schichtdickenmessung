import os
import csv
import datetime

from layer_thickness_app.services.database_service import DatabaseService

class ExportService:
    """
    Exports measurement data from the DatabaseService to a CSV file.
    """

    def __init__(self, db_service: DatabaseService):
        """
        Initializes the export service.

        Args:
            db_service (DatabaseService): An instance of the DatabaseService.
            export_dir (str): The path to the folder where CSV files will be saved.
        """
        self.db_service = db_service

    def export_to_csv(self, export_dir: str) -> str:
        """
        Fetches all measurements and saves them to a timestamped CSV file.

        The CSV includes all columns from the database (id, Date, Name, etc.).

        Returns:
            str: The full path to the generated CSV file, or an empty string if
                 the export failed or there was no data.
        """
        print("Starting data export...")
        data = self.db_service.get_measurements()
        # Ensure the export directory exists
        os.makedirs(export_dir, exist_ok=True)

        if not data:
            print("No data found in the database to export.")
            return ""

        # Generate a unique filename based on the current time
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"measurements_export_{timestamp}.csv"
        filepath = os.path.join(export_dir, filename)

        # Get the headers from the first row of data
        headers = data[0].keys()

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()  # Write the header row
                writer.writerows(data) # Write all data rows

            print(f"Successfully exported {len(data)} rows to {filepath}")
            return filepath
        except IOError as e:
            print(f"Error writing CSV file: {e}")
            return ""
        except Exception as e:
            print(f"An unexpected error occurred during export: {e}")
            return ""

