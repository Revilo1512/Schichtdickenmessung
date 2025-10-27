import csv
import zipfile
import tempfile
import os
import base64
import shutil
from typing import Tuple

from layer_thickness_app.services.database_service import DatabaseService


class ImportService:
    """
    Imports measurement data from a ZIP archive into the DatabaseService.
    
    The ZIP archive is expected to contain:
    - A 'measurements.csv' file.
    - An 'img/' folder containing the images referenced in the CSV.
    """

    # Define the columns required by the save_measurement method
    # RefImage and MatImage will now be paths in the CSV, but converted to base64
    REQUIRED_COLUMNS = {'Date', 'Name', 'Layer', 'Wavelength', 'RefImage', 'MatImage', 'Shelf', 'Book', 'Page'}

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

    def _read_image_as_base64(self, img_path: str) -> str | None:
        """Reads an image file and returns it as a base64 string."""
        if not os.path.exists(img_path):
            print(f"Image not found at path: {img_path}")
            return None
        try:
            with open(img_path, 'rb') as f:
                encoded_string = base64.b64encode(f.read()).decode('utf-8')
            return encoded_string
        except Exception as e:
            print(f"Error reading image {img_path}: {e}")
            return None

    def import_from_zip(self, zip_filepath: str) -> Tuple[int, int]:
        """
        Reads a ZIP archive, extracts it, and imports its data into the database.
        """
        print(f"Starting import from {zip_filepath}...")
        success_count = 0
        fail_count = 0
        temp_dir = tempfile.mkdtemp()

        try:
            # --- 1. Extract ZIP to temp directory ---
            with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            csv_path = os.path.join(temp_dir, 'measurements.csv')
            if not os.path.exists(csv_path):
                print(f"Error: 'measurements.csv' not found in the ZIP file.")
                return (0, 0)

            # --- 2. Process the CSV file ---
            # Increase field size limit for safety, though paths are small
            csv.field_size_limit(10485760) 

            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                if not reader.fieldnames:
                    print(f"Error: CSV file is empty or has no header: {csv_path}")
                    return (0, 0)

                reader_headers = set(reader.fieldnames)
                if not self.REQUIRED_COLUMNS.issubset(reader_headers):
                    missing = self.REQUIRED_COLUMNS - reader_headers
                    print(f"Error: CSV file is missing required columns: {missing}")
                    return (0, 0)

                # --- 3. Process each row ---
                for i, row in enumerate(reader, start=2):
                    try:
                        data_to_save = {}
                        for col in self.REQUIRED_COLUMNS:
                            data_to_save[col] = row[col]

                        # --- FIX for 'could not convert string to float: ''' ---
                        # 'Layer' is NOT NULL, so it must be valid
                        try:
                            data_to_save['Layer'] = float(row['Layer'])
                        except (ValueError, TypeError):
                            print(f"Error processing row {i}: Invalid or missing data for 'Layer'. Expected float, got '{row.get('Layer', 'N/A')}'")
                            fail_count += 1
                            continue # Skip to next row

                        # 'Wavelength' is nullable, so it can be None
                        try:
                            if row.get('Wavelength') is not None and row['Wavelength'] != '':
                                data_to_save['Wavelength'] = float(row['Wavelength'])
                            else:
                                data_to_save['Wavelength'] = None
                        except (ValueError, TypeError):
                            print(f"Error processing row {i}: Invalid data type for 'Wavelength', setting to NULL. Got '{row.get('Wavelength', 'N/A')}'")
                            data_to_save['Wavelength'] = None
                        # --- END FIX ---
                        
                        # 'Date' is already handled by the REQUIRED_COLUMNS loop

                        # --- 4. Convert Image Paths to Base64 ---
                        ref_img_path = os.path.join(temp_dir, row['RefImage'])
                        mat_img_path = os.path.join(temp_dir, row['MatImage'])

                        ref_b64 = self._read_image_as_base64(ref_img_path)
                        mat_b64 = self._read_image_as_base64(mat_img_path)

                        if ref_b64 is None or mat_b64 is None:
                            print(f"Error processing row {i}: Could not read image files.")
                            fail_count += 1
                            continue

                        data_to_save['RefImage'] = ref_b64
                        data_to_save['MatImage'] = mat_b64
                        
                        # --- 5. Save to DB ---
                        new_id = self.db_service.save_measurement(data_to_save)
                        if new_id > -1:
                            success_count += 1
                        else:
                            print(f"Error saving row {i} (database service failed).")
                            fail_count += 1

                    except Exception as e:
                        print(f"An unexpected error occurred processing row {i}: {e}")
                        fail_count += 1

        except FileNotFoundError:
            print(f"Error: File not found at {zip_filepath}")
            return (0, 0)
        except zipfile.BadZipFile:
            print(f"Error: Bad ZIP file {zip_filepath}")
            return (0, 0)
        except Exception as e:
            print(f"Error reading ZIP file {zip_filepath}: {e}")
            return (0, 0)
        finally:
            # --- 6. Clean up temp directory ---
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"Error cleaning up temp directory {temp_dir}: {e}")

        print(f"Import complete: {success_count} rows succeeded, {fail_count} rows failed.")
        return (success_count, fail_count)