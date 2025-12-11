import os
import csv
import datetime
import base64
import tempfile
import shutil
import zipfile
from pathlib import Path
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
        self.image_dir_path = Path(self.db_service.db_path).parent / "images"

    def export_to_zip(
        self, 
        export_dir: str,
        name_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        shelf: Optional[str] = None,
        book: Optional[str] = None,
        page: Optional[str] = None,
        note_filter: Optional[str] = None
    ) -> str:
        """
        Fetches filtered measurements, copies images from the 'data/images'
        folder, creates a CSV, and saves them as a single timestamped ZIP file.

        Returns:
            str: The full path to the generated ZIP file, or an empty string if
                 the export failed or there was no data.
        """
        print("Starting data export to ZIP...")
        
        data = self.db_service.get_all_filtered_measurements(
            name_filter, start_date, end_date, shelf, book, page, note_filter
        )
        
        if not data:
            print("No data found matching filters to export.")
            return ""

        temp_dir = tempfile.mkdtemp()
        img_dir = os.path.join(temp_dir, 'img')
        csv_path = os.path.join(temp_dir, 'measurements.csv')
        
        try:
            os.makedirs(img_dir, exist_ok=True)
            csv_data = [] # new list of dicts for the CSV

            # --- 1. Copy images, create new rows for CSV ---
            for row in data:
                row_dict = dict(row) # Make a mutable copy
                db_id = row_dict['id']
                
                # Get the source filenames from the DB
                ref_img_filename = row_dict.get('RefImage')
                mat_img_filename = row_dict.get('MatImage')

                # Define relative paths for the CSV (inside the zip)
                ref_img_csv_path = f"img/ref_{db_id}.png"
                mat_img_csv_path = f"img/mat_{db_id}.png"
                
                # Define full destination paths (in the temp zip folder)
                ref_img_dest_path = os.path.join(img_dir, f"ref_{db_id}.png")
                mat_img_dest_path = os.path.join(img_dir, f"mat_{db_id}.png")

                # Copy images from data/images to the temp folder
                if ref_img_filename:
                    ref_img_src_path = self.image_dir_path / ref_img_filename
                    if ref_img_src_path.exists():
                        shutil.copy(ref_img_src_path, ref_img_dest_path)
                    else:
                        print(f"Warning: Source image not found: {ref_img_src_path}")
                
                if mat_img_filename:
                    mat_img_src_path = self.image_dir_path / mat_img_filename
                    if mat_img_src_path.exists():
                        shutil.copy(mat_img_src_path, mat_img_dest_path)
                    else:
                        print(f"Warning: Source image not found: {mat_img_src_path}")

                # Update row dict with paths *relative to the zip*
                row_dict['RefImage'] = ref_img_csv_path
                row_dict['MatImage'] = mat_img_csv_path
                
                csv_data.append(row_dict)

            # --- 2. Write the new data (with paths) to the CSV ---
            if not csv_data:
                print("No data to write to CSV.") # Should be caught by 'if not data'
                return ""

            # Get headers from the first processed row and exclude 'id'
            all_headers = list(csv_data[0].keys())
            export_headers = [h for h in all_headers if h != 'id']
            
            # Ensure 'Note' is last if it exists, for better readability (optional)
            if 'Note' in export_headers:
                export_headers.remove('Note')
                export_headers.append('Note')

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