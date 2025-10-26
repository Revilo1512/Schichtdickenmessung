import base64
import cv2
import numpy as np
from typing import Dict, Any

# import gui
from layer_thickness_app.gui.main_window import MainWindow

# import services
from layer_thickness_app.services.camera_service import CameraService
from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.material_service import MaterialService
from layer_thickness_app.services.calculation_service import CalculationService
from layer_thickness_app.services.export_service import ExportService
from layer_thickness_app.services.import_service import ImportService


class MainController:
    """
    The central controller that manages the GUI and services.
    Connects the signals to functions.
    """
    def __init__(self):
        # The controller "owns" all the major objects in the application.

        self.db_service = DatabaseService("data/measurements.db")
        self.export_service = ExportService(self.db_service)
        self.import_service = ImportService(self.db_service)
        self.material_service = MaterialService()
        self.calculation_service = CalculationService()
        self.camera_service = CameraService()

        self.view = MainWindow(self.db_service)

        # Store the view's pages for easy access
        self.measurement_page = self.view.measure_interface
        try:
            data = self.material_service.get_material_data()
            self.measurement_page.populate_material_selector(data)
        except Exception as e:
            print(f"Controller: An error occurred - {e}")
            print("Couldn't load material data")
        
        self._connect_signals()

    def show_window(self):
        """Makes the main window visible."""
        self.view.show()

    def _connect_signals(self):
        """Connects all the UI signals to the controller's methods."""
        
        if hasattr(self.measurement_page, 'calculate_button'):
            self.measurement_page.calculate_button.clicked.connect(self.on_start_calc)
        
        if hasattr(self.measurement_page, 'ref_image_button'):
            self.measurement_page.ref_image_button.clicked.connect(self.on_take_reference_image)
            
        if hasattr(self.measurement_page, 'mat_image_button'):
            self.measurement_page.mat_image_button.clicked.connect(self.on_take_material_image)
        
        # TODO: Connect self.measurement_page.reset_button
    
    def on_start_calc(self):
        """
        Triggered when the user clicks the 'Calculate' button.
        Orchestrates the entire calculation process and saves if requested.
        """
        print("Controller: Calculation started...")
        self.measurement_page.set_result_text("Calculating...")


        # --- 1. Get Data from View ---
        try:
            ref_image = self.measurement_page.reference_image
            mat_image = self.measurement_page.material_image
            material_path = self.measurement_page.material_selector.get_selected_path()
            wavelength_um = self.measurement_page.wavelength_combo.currentData() 
        except Exception as e:
            print(f"Controller: ERROR - Could not get data from UI: {e}")
            self.measurement_page.set_result_text("Error: UI components missing.")
            return
        

        # --- 2. Validate Data ---
        if ref_image is None or mat_image is None:
            print("Controller: ERROR - Reference or material image is missing.")
            self.measurement_page.set_result_text("Error: Missing one or both images.")
            return
            
        if material_path is None:
            print("Controller: ERROR - No material dataset selected.")
            self.measurement_page.set_result_text("Error: No material selected.")
            return
            
        if wavelength_um is None:
            print("Controller: ERROR - No wavelength selected.")
            self.measurement_page.set_result_text("Error: No wavelength selected.")
            return
        
        try:
            shelf, book, page = material_path.split('/')
        except ValueError:
            error_msg = f"Internal Error: Invalid material path format: {material_path}"
            print(f"Controller: ERROR - {error_msg}")
            self.measurement_page.set_result_text(error_msg)
            return
            
        print(f"Controller: Validated data. Calculating with:\n  Material: {material_path}\n  Wavelength: {wavelength_um}µm")

        # --- 3. Call Service and Display Result ---
        try:
            thickness_nm, error_msg = self.calculation_service.calculate_thickness(
                ref_image, mat_image, shelf, book, page, wavelength_um
            )
            
            if error_msg:
                print(f"Controller: ERROR - {error_msg}")
                self.measurement_page.set_result_text(error_msg)
            else:
                result_text = f"{thickness_nm:.2f} nm"
                print(f"Controller: Calculation successful. Result: {result_text}")
                self.measurement_page.set_result_text(f"<b>{result_text}</b>")
                
                # --- 4. Save to Database (if checked) ---
                if self.measurement_page.save_measurement_checkbox.isChecked():
                    self._save_measurement_to_db(
                        thickness=thickness_nm,
                        ref_image=ref_image,
                        mat_image=mat_image,
                        shelf=shelf,
                        book=book,
                        page=page
                    )
                    # Append "Saved!" to the result
                    self.measurement_page.set_result_text(result_text, append=True)

        except Exception as e:
            # Catch any unexpected errors from the service
            error_str = f"Unhandled Error: {e}"
            print(f"Controller: UNHANDLED EXCEPTION in calculation: {e}")
            self.measurement_page.set_result_text(error_str)

    def _save_measurement_to_db(self, thickness: float, ref_image: np.ndarray, 
                                mat_image: np.ndarray, shelf: str, book: str, page: str):
        """
        Helper method to serialize images and save a measurement to the database.
        """
        print("Controller: Saving measurement to database...")
        try:
            # Get name from UI
            if self.measurement_page.use_name_checkbox.isChecked():
                name = self.measurement_page.name_field.text()
                if not name:
                    name = "Guest" # Default if box is checked but field is empty
            else:
                name = "Guest"

            # Serialize images to Base64 text
            _, ref_img_encoded = cv2.imencode('.png', ref_image)
            ref_img_b64 = base64.b64encode(ref_img_encoded).decode('utf-8')
            
            _, mat_img_encoded = cv2.imencode('.png', mat_image)
            mat_img_b64 = base64.b64encode(mat_img_encoded).decode('utf-8')

            # Create data dictionary matching database schema
            db_data = {
                "Name": name,
                "Layer": thickness,
                "RefImage": ref_img_b64,
                "MatImage": mat_img_b64,
                "Shelf": shelf,
                "Book": book,
                "Page": page
            }
            
            # Call database service
            row_id = self.db_service.save_measurement(db_data)
            print(f"Controller: Measurement saved successfully with ID: {row_id}")

        except Exception as e:
            print(f"Controller: ERROR - Failed to save measurement: {e}")
            self.measurement_page.set_result_text("Error: Failed to save measurement.", append=True)

    def on_take_reference_image(self):
        """Handles the 'Take ReferenceImage' button click."""
        print("Controller: Taking Reference Image...")
        self.measurement_page.set_result_text("Taking Reference Image...") # Give feedback
        image_data = self.camera_service.capture_image()
        
        if image_data is not None:
            self.measurement_page.set_image(image_data, "reference")
            print("Controller: Reference Image captured and displayed.")
            self.measurement_page.set_result_text("Result...") # Reset result text
        else:
            print("Controller: ERROR - Failed to capture reference image.")
            self.measurement_page.set_result_text("Error: Failed to capture reference image.")

    def on_take_material_image(self):
        """Handles the 'Take Material Image' button click."""
        print("Controller: Taking Material Image...")
        self.measurement_page.set_result_text("Taking Material Image...") # Give feedback
        image_data = self.camera_service.capture_image()
        
        if image_data is not None:
            self.measurement_page.set_image(image_data, "material")
            print("Controller: Material Image captured and displayed.")
            self.measurement_page.set_result_text("Result...") # Reset result text
        else:
            print("Controller: ERROR - Failed to capture material image.")
            self.measurement_page.set_result_text("Error: Failed to capture material image.")
    