import os
import csv
import datetime
import base64
import tempfile
import shutil
import zipfile
from typing import Optional

from layer_thickness_app.services.database_service import DatabaseService

class ExportService:
    """
    Exports measurement data from the DatabaseService to a ZIP archive.
    
    The archive will contain:
    - 'measurements.csv' (with paths to images)
    - 'img/' folder (with all the .png image files)
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

    def _save_base64_as_image(self, b64_string: str, out_path: str):
        """Decodes a base64 string and saves it as a binary file."""
        try:
            img_data = base64.b64decode(b64_string)
            with open(out_path, 'wb') as f:
                f.write(img_data)
        except Exception as e:
            print(f"Error decoding/saving image {out_path}: {e}")

    def export_to_zip(
        self, 
        export_dir: str,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        shelf: Optional[str] = None,
        book: Optional[str] = None,
        page: Optional[str] = None
    ) -> str:
        """
        Fetches filtered measurements, creates a CSV and image folder,
        and saves them as a single timestamped ZIP file.

        Returns:
            str: The full path to the generated ZIP file, or an empty string if
                 the export failed or there was no data.
        """
        print("Starting data export to ZIP...")
        
        data = self.db_service.get_all_filtered_measurements(
            name_filter, start_date, end_date, shelf, book, page
        )
        
        if not data:
            print("No data found matching filters to export.")
            return ""

        temp_dir = tempfile.mkdtemp()
        img_dir = os.path.join(temp_dir, 'img')
        csv_path = os.path.join(temp_dir, 'measurements.csv')
        
        try:
            os.makedirs(img_dir, exist_ok=True)
            csv_data = [] # We'll build a new list of dicts for the CSV

            # --- 1. Process data: save images, create new rows for CSV ---
            for row in data:
                row_dict = dict(row) # Make a mutable copy
                db_id = row_dict['id']
                
                # Pop the base64 data
                ref_b64 = row_dict.pop('RefImage', None)
                mat_b64 = row_dict.pop('MatImage', None)

                # Define relative paths
                ref_img_rel_path = f"img/ref_{db_id}.png"
                mat_img_rel_path = f"img/mat_{db_id}.png"
                
                # Define full paths for saving
                ref_img_full_path = os.path.join(temp_dir, ref_img_rel_path)
                mat_img_full_path = os.path.join(temp_dir, mat_img_rel_path)

                # Save images
                if ref_b64:
                    self._save_base64_as_image(ref_b64, ref_img_full_path)
                if mat_b64:
                    self._save_base64_as_image(mat_b64, mat_img_full_path)
                
                # Update row dict with paths
                row_dict['RefImage'] = ref_img_rel_path
                row_dict['MatImage'] = mat_img_rel_path
                
                csv_data.append(row_dict)

            # --- 2. Write the new data (with paths) to the CSV ---
            if not csv_data:
                print("No data to write to CSV.") # Should be caught by 'if not data'
                return ""

            # Get headers from the first processed row and exclude 'id'
            all_headers = list(csv_data[0].keys())
            export_headers = [h for h in all_headers if h != 'id']

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=export_headers, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(csv_data)

            # --- 3. Create the ZIP file ---
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"measurements_export_{timestamp}"
            zip_base_path = os.path.join(export_dir, zip_name)
            
            # shutil.make_archive creates 'zip_name.zip'
            zip_filepath = shutil.make_archive(
                base_name=zip_base_path,
                format='zip',
                root_dir=temp_dir
            )
            
            print(f"Successfully exported {len(data)} rows to {zip_filepath}")
            return zip_filepath
            
        except Exception as e:
            print(f"An unexpected error occurred during export: {e}")
            return ""
        finally:
            # --- 4. Clean up temp directory ---
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"Error cleaning up temp directory {temp_dir}: {e}")