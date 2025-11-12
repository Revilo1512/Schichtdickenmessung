import csv
import zipfile
import tempfile
import os
import base64
import shutil
import uuid
from typing import Tuple
from pathlib import Path
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
    REQUIRED_COLUMNS = {'Date', 'Name', 'Layer', 'Wavelength', 'RefImage', 'MatImage', 'Shelf', 'Book', 'Page', 'Note'}

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

        self.image_dir_path = Path(self.db_service.db_path).parent / "images"
        self.image_dir_path.mkdir(parents=True, exist_ok=True)

    

    def import_from_zip(self, zip_filepath: str) -> Tuple[int, int]:
        """
        Reads a ZIP archive, extracts it, copies images to the data/images
        folder, and imports metadata into the database.
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
                            # Handle None for 'Note' column if it's missing in the row
                            data_to_save[col] = row.get(col) 
                            
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
                        
                        # 'Date', 'Name', 'Shelf', 'Book', 'Page', 'Note' are handled by the loop

                        # --- 4. Copy images and save filenames ---
                        
                        # Get paths from CSV (relative to temp_dir)
                        ref_img_rel_path = row['RefImage']
                        mat_img_rel_path = row['MatImage']

                        # Get source paths (in the extracted zip folder)
                        ref_img_src_path = os.path.join(temp_dir, ref_img_rel_path)
                        mat_img_src_path = os.path.join(temp_dir, mat_img_rel_path)

                        if not os.path.exists(ref_img_src_path) or not os.path.exists(mat_img_src_path):
                            print(f"Error processing row {i}: Image file not found in ZIP. Missing {ref_img_src_path} or {mat_img_src_path}")
                            fail_count += 1
                            continue

                        # Generate new unique filenames for the database
                        ref_img_name_db = f"ref_{uuid.uuid4()}.png"
                        mat_img_name_db = f"mat_{uuid.uuid4()}.png"

                        # Define destination paths (in the data/images folder)
                        ref_img_dest_path = self.image_dir_path / ref_img_name_db
                        mat_img_dest_path = self.image_dir_path / mat_img_name_db

                        # Copy the files
                        try:
                            shutil.copy(ref_img_src_path, ref_img_dest_path)
                            shutil.copy(mat_img_src_path, mat_img_dest_path)
                        except Exception as copy_e:
                            print(f"Error processing row {i}: Could not copy image files. {copy_e}")
                            fail_count += 1
                            continue
                        
                        # Store the *new filenames* in the data to be saved
                        data_to_save['RefImage'] = ref_img_name_db
                        data_to_save['MatImage'] = mat_img_name_db
                        
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