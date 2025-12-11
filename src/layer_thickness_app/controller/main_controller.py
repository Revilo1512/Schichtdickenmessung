import base64
import cv2
import numpy as np
import uuid
import os
from typing import Dict, Any
from PyQt6.QtGui import QIcon

# import gui
from layer_thickness_app.gui.main_window import MainWindow

# import services
from layer_thickness_app.services.camera_service import CameraService
from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.material_service import MaterialService
from layer_thickness_app.services.calculation_service import CalculationService
from layer_thickness_app.services.export_service import ExportService
from layer_thickness_app.services.import_service import ImportService
from layer_thickness_app.config.config import AppConfig # Use new config


class MainController:
    """
    The central controller that manages the GUI and services.
    Connects the signals to functions.
    """
    def __init__(self, config: AppConfig):
        # The controller "owns" all the major objects in the application.
        self.config = config

        self.db_service = DatabaseService("data/measurements.db")
        self.export_service = ExportService(self.db_service)
        self.import_service = ImportService(self.db_service)
        self.material_service = MaterialService()
        self.calculation_service = CalculationService()
        self.camera_service = CameraService() # Camera service is created here

        # Pass services and config to the main window
        self.view = MainWindow(
            db_service=self.db_service,
            import_service=self.import_service,
            export_service=self.export_service,
            camera_service=self.camera_service, # Pass camera service
            config=self.config
        )
        icon_path = r"src\layer_thickness_app\gui\resources\duck_icon.svg"
        if os.path.exists(icon_path):
            self.view.setWindowIcon(QIcon(icon_path))
        else:
            print(f"Warning: Icon file not found at {icon_path}")

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
        # Window size is handled by MainWindow itself

    def _connect_signals(self):
        """Connects all the UI signals to the controller's methods."""
        
        if hasattr(self.measurement_page, 'calculate_button'):
            self.measurement_page.calculate_button.clicked.connect(self.on_start_calc)
        
        if hasattr(self.measurement_page, 'ref_image_button'):
            self.measurement_page.ref_image_button.clicked.connect(self.on_take_reference_image)
            
        if hasattr(self.measurement_page, 'mat_image_button'):
            self.measurement_page.mat_image_button.clicked.connect(self.on_take_material_image)
        
        if hasattr(self.measurement_page, 'reset_button'):
            self.measurement_page.reset_button.clicked.connect(self.on_reset_measurement)
            
        # Connect config changed signal
        self.measurement_page.config_changed.connect(self._on_measure_config_changed)

        try:
            # When history page deletes data, tell CSV page to refresh filters
            self.view.history_interface.data_changed.connect(
                self.view.csv_interface._load_filter_suggestions
            )
            
            # When CSV page imports data, tell history page to refresh filters
            self.view.csv_interface.data_changed.connect(
                self.view.history_interface._load_name_suggestions
            )
            
            print("Controller: Connected data_changed signals between pages.")
        except AttributeError as e:
            print(f"Controller Warning: Could not connect data_changed signals. {e}")
    
    def _on_measure_config_changed(self):
        """Re-enables the calculate button when config changes."""
        self.measurement_page.calculate_button.setEnabled(True)

    def on_reset_measurement(self):
        """Resets the measurement page UI and internal data."""
        print("Controller: Resetting measurement page...")
        self.measurement_page.reset_all()
        
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
            self.measurement_page._show_info_bar("UI Error", "Could not get data from UI components.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
        

        # --- 2. Validate Data ---
        if ref_image is None or mat_image is None:
            print("Controller: ERROR - Reference or material image is missing.")
            self.measurement_page._show_info_bar("Validation Error", "Missing one or both images.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
            
        if material_path is None:
            print("Controller: ERROR - No material dataset selected.")
            self.measurement_page._show_info_bar("Validation Error", "No material selected.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
            
        if wavelength_um is None:
            print("Controller: ERROR - No wavelength selected.")
            self.measurement_page._show_info_bar("Validation Error", "No wavelength selected.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
        
        try:
            shelf, book, page = material_path.split('/')
        except ValueError:
            error_msg = f"Internal Error: Invalid material path format: {material_path}"
            print(f"Controller: ERROR - {error_msg}")
            self.measurement_page._show_info_bar("Internal Error", error_msg, is_error=True)
            self.measurement_page.set_result_text("Error")
            return
            
        print(f"Controller: Validated data. Calculating with:\n  Material: {material_path}\n  Wavelength: {wavelength_um}µm")

        # --- 3. Call Service and Display Result ---
        try:
            thickness_nm, error_msg = self.calculation_service.calculate_thickness(
                ref_image, mat_image, shelf, book, page, wavelength_um
            )
            
            if error_msg:
                print(f"Controller: ERROR - {error_msg}")
                self.measurement_page._show_info_bar("Calculation Error", error_msg, is_error=True)
                self.measurement_page.set_result_text("Error")
            else:
                result_text = f"{thickness_nm:.2f} nm"
                print(f"Controller: Calculation successful. Result: {result_text}")
                self.measurement_page.set_result_text(f"<b>{result_text}</b>")
                
                # --- 4. Save to Database (if checked) ---
                if self.measurement_page.save_measurement_checkbox.isChecked():
                    self._save_measurement_to_db(
                        thickness=thickness_nm,
                        wavelength=wavelength_um, # Pass wavelength
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
            self.measurement_page._show_info_bar("Unhandled Error", str(e), is_error=True)
            self.measurement_page.set_result_text("Error")
        
        finally:
            # Deactivate button after calculation attempt
            self.measurement_page.calculate_button.setEnabled(False)

    def _save_measurement_to_db(self, thickness: float, wavelength: float, 
                                ref_image: np.ndarray, mat_image: np.ndarray, 
                                shelf: str, book: str, page: str):
        """
        Helper method to save images to disk and save the measurement 
        (with image filenames) to the database.
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
                
            # Get note from UI
            note = self.measurement_page.note_field.text()

            # Generate unique filenames
            ref_img_name = f"ref_{uuid.uuid4()}.png"
            mat_img_name = f"mat_{uuid.uuid4()}.png"
            
            # Get the image directory path from the database service
            image_dir = self.db_service.image_dir_path
            
            # Create full save paths
            ref_img_path = os.path.join(image_dir, ref_img_name)
            mat_img_path = os.path.join(image_dir, mat_img_name)

            # Save images using cv2.imwrite
            cv2.imwrite(ref_img_path, ref_image)
            cv2.imwrite(mat_img_path, mat_image)
            
            print(f"Controller: Saved images to {ref_img_path} and {mat_img_path}")

            # Create data dictionary matching database schema
            db_data = {
                "Name": name,
                "Layer": thickness,
                "Wavelength": wavelength,
                "RefImage": ref_img_name,
                "MatImage": mat_img_name,
                "Shelf": shelf,
                "Book": book,
                "Page": page,
                "Note": note if note else None
            }
            
            # Call database service
            row_id = self.db_service.save_measurement(db_data)
            print(f"Controller: Measurement saved successfully with ID: {row_id}")
            self.measurement_page._show_info_bar("Success", f"Measurement saved with ID: {row_id}", is_error=False)

        except Exception as e:
            print(f"Controller: ERROR - Failed to save measurement: {e}")
            self.measurement_page._show_info_bar("Save Error", "Failed to save measurement.", is_error=True)

    def on_take_reference_image(self):
        """Handles the 'Take ReferenceImage' button click."""
        # Check if camera is connected first
        if not self.camera_service.get_status()["connected"]:
            print("Controller: ERROR - Cannot capture image, camera is not connected.")
            self.measurement_page._show_info_bar("Camera Error", "Camera is not connected. Please connect it on the Home page.", is_error=True)
            return

        print("Controller: Taking Reference Image...")
        self.measurement_page.set_result_text("Taking Reference Image...")
        image_data = self.camera_service.capture_image()
        
        if image_data is not None:
            self.measurement_page.set_image(image_data, "reference")
            print("Controller: Reference Image captured and displayed.")
            self.measurement_page.set_result_text("Result...")
            self.measurement_page.calculate_button.setEnabled(True)
        else:
            print("Controller: ERROR - Failed to capture reference image.")
            self.measurement_page._show_info_bar("Capture Error", "Failed to capture reference image.", is_error=True)
            self.measurement_page.set_result_text("Error")

    def on_take_material_image(self):
        """Handles the 'Take Material Image' button click."""
        # Check if camera is connected first
        if not self.camera_service.get_status()["connected"]:
            print("Controller: ERROR - Cannot capture image, camera is not connected.")
            self.measurement_page._show_info_bar("Camera Error", "Camera is not connected. Please connect it on the Home page.", is_error=True)
            return
            
        print("Controller: Taking Material Image...")
        self.measurement_page.set_result_text("Taking Material Image...")
        image_data = self.camera_service.capture_image()
        
        if image_data is not None:
            self.measurement_page.set_image(image_data, "material")
            print("Controller: Material Image captured and displayed.")
            self.measurement_page.set_result_text("Result...")
            self.measurement_page.calculate_button.setEnabled(True)
        else:
            print("Controller: ERROR - Failed to capture material image.")
            self.measurement_page._show_info_bar("Capture Error", "Failed to capture material image.", is_error=True)
            self.measurement_page.set_result_text("Error")