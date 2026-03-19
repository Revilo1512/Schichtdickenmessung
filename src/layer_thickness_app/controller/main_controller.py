import base64
import cv2
import numpy as np
import uuid
import os
import logging
from typing import Any
from PyQt6.QtGui import QIcon

from layer_thickness_app.gui.main_window import MainWindow
from layer_thickness_app.services.camera_service import CameraService
from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.material_service import MaterialService
from layer_thickness_app.services.calculation_service import CalculationService
from layer_thickness_app.services.export_service import ExportService
from layer_thickness_app.services.import_service import ImportService
from layer_thickness_app.config.config import AppConfig 

logger = logging.getLogger(__name__)

class MainController:
    """
    The central controller that manages the GUI and services.
    Connects the signals to functions.
    """
    def __init__(self, config: AppConfig):
        self.config = config

        self.db_service = DatabaseService("data/measurements.db")
        self.export_service = ExportService(self.db_service)
        self.import_service = ImportService(self.db_service)
        self.material_service = MaterialService()
        self.calculation_service = CalculationService()
        self.camera_service = CameraService()

        self.view = MainWindow(
            db_service=self.db_service,
            import_service=self.import_service,
            export_service=self.export_service,
            camera_service=self.camera_service,
            config=self.config
        )
        icon_path = r"src\layer_thickness_app\gui\resources\duck_icon.svg"
        if os.path.exists(icon_path):
            self.view.setWindowIcon(QIcon(icon_path))
        else:
            logger.warning("Icon file not found at %s", icon_path)

        self.measurement_page = self.view.measure_interface
        try:
            data = self.material_service.get_material_data()
            self.measurement_page.populate_material_selector(data)
        except Exception as e:
            logger.error("Couldn't load material data: %s", e)
        
        self._connect_signals()

    def show_window(self):
        self.view.show()

    def _connect_signals(self):
        """Verbindet View-Signale mit Controller-Methoden (Saubere Entkopplung)"""
        self.measurement_page.calculation_requested.connect(self.on_start_calc)
        self.measurement_page.capture_reference_requested.connect(self.on_take_reference_image)
        self.measurement_page.capture_material_requested.connect(self.on_take_material_image)
        self.measurement_page.reset_requested.connect(self.on_reset_measurement)
        self.measurement_page.config_changed.connect(self._on_measure_config_changed)

        try:
            self.view.history_interface.data_changed.connect(
                self.view.csv_interface._load_filter_suggestions
            )
            self.view.csv_interface.data_changed.connect(
                self.view.history_interface._load_name_suggestions
            )
            logger.info("Connected data_changed signals between pages.")
        except AttributeError as e:
            logger.warning("Could not connect data_changed signals. %s", e)
    
    def _on_measure_config_changed(self):
        """Re-enables the calculate button when config changes."""
        self.measurement_page.set_calculation_enabled(True)

    def on_reset_measurement(self):
        logger.info("Resetting measurement page...")
        self.measurement_page.reset_all()
        
    def on_start_calc(self):
        logger.info("Calculation started...")
        self.measurement_page.set_result_text("Calculating...")

        # --- 1. Get Data from View via Interface ---
        ui_data = self.measurement_page.get_measurement_data()
        ref_image = ui_data["ref_image"]
        mat_image = ui_data["mat_image"]
        material_path = ui_data["material_path"]
        wavelength_um = ui_data["wavelength_um"]

        # --- 2. Validate Data ---
        if ref_image is None or mat_image is None:
            logger.error("Reference or material image is missing.")
            self.measurement_page.show_info_bar("Validation Error", "Missing one or both images.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
            
        if not material_path:
            logger.error("No material dataset selected.")
            self.measurement_page.show_info_bar("Validation Error", "No material selected.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
            
        if wavelength_um is None:
            logger.error("No wavelength selected.")
            self.measurement_page.show_info_bar("Validation Error", "No wavelength selected.", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
        
        try:
            shelf, book, page = material_path.split('/')
        except ValueError:
            logger.error("Invalid material path format: %s", material_path)
            self.measurement_page.show_info_bar("Internal Error", f"Invalid format: {material_path}", is_error=True)
            self.measurement_page.set_result_text("Error")
            return
            
        logger.info("Validated data. Calculating with Material: %s, Wavelength: %sµm", material_path, wavelength_um)

        # --- 3. Call Service and Display Result ---
        try:
            thickness_nm, error_msg = self.calculation_service.calculate_thickness(
                ref_image, mat_image, shelf, book, page, wavelength_um
            )
            
            if error_msg:
                logger.error("Calculation Error: %s", error_msg)
                self.measurement_page.show_info_bar("Calculation Error", error_msg, is_error=True)
                self.measurement_page.set_result_text("Error")
            elif thickness_nm is not None:
                result_text = f"{thickness_nm:.2f} nm"
                logger.info("Calculation successful. Result: %s", result_text)
                self.measurement_page.set_result_text(f"<b>{result_text}</b>")
                
                # --- 4. Save to Database (if checked) ---
                if ui_data["save_checked"]:
                    self._save_measurement_to_db(
                        thickness=thickness_nm,
                        wavelength=wavelength_um,
                        ref_image=ref_image,
                        mat_image=mat_image,
                        shelf=shelf,
                        book=book,
                        page=page,
                        ui_data=ui_data
                    )
                    self.measurement_page.set_result_text(result_text, append=True)

        except Exception as e:
            logger.exception("UNHANDLED EXCEPTION in calculation: %s", e)
            self.measurement_page.show_info_bar("Unhandled Error", str(e), is_error=True)
            self.measurement_page.set_result_text("Error")
        
        finally:
            self.measurement_page.set_calculation_enabled(False)

    def _save_measurement_to_db(self, thickness: float, wavelength: float, 
                                ref_image: np.ndarray, mat_image: np.ndarray, 
                                shelf: str, book: str, page: str, ui_data: dict[str, Any]):
        logger.info("Saving measurement to database...")
        try:
            name = ui_data["name"] if (ui_data["use_name"] and ui_data["name"]) else "Guest"
            note = ui_data["note"]

            ref_img_name = f"ref_{uuid.uuid4()}.png"
            mat_img_name = f"mat_{uuid.uuid4()}.png"
            
            image_dir = self.db_service.image_dir_path
            ref_img_path = str(image_dir / ref_img_name)
            mat_img_path = str(image_dir / mat_img_name)

            cv2.imwrite(ref_img_path, ref_image)
            cv2.imwrite(mat_img_path, mat_image)
            
            logger.info("Saved images to %s and %s", ref_img_path, mat_img_path)

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
            
            row_id = self.db_service.save_measurement(db_data)
            logger.info("Measurement saved successfully with ID: %s", row_id)
            self.measurement_page.show_info_bar("Success", f"Measurement saved with ID: {row_id}", is_error=False)

        except Exception as e:
            logger.exception("Failed to save measurement: %s", e)
            self.measurement_page.show_info_bar("Save Error", "Failed to save measurement.", is_error=True)

    def on_take_reference_image(self):
        if not self.camera_service.get_status()["connected"]:
            logger.error("Cannot capture image, camera is not connected.")
            self.measurement_page.show_info_bar("Camera Error", "Camera is not connected. Please connect it on the Home page.", is_error=True)
            return

        logger.info("Taking Reference Image...")
        self.measurement_page.set_result_text("Taking Reference Image...")
        image_data = self.camera_service.capture_image()
        
        if image_data is not None:
            self.measurement_page.set_image(image_data, "reference")
            logger.info("Reference Image captured and displayed.")
            self.measurement_page.set_result_text("Result...")
            self.measurement_page.set_calculation_enabled(True)
        else:
            logger.error("Failed to capture reference image.")
            self.measurement_page.show_info_bar("Capture Error", "Failed to capture reference image.", is_error=True)
            self.measurement_page.set_result_text("Error")

    def on_take_material_image(self):
        if not self.camera_service.get_status()["connected"]:
            logger.error("Cannot capture image, camera is not connected.")
            self.measurement_page.show_info_bar("Camera Error", "Camera is not connected. Please connect it on the Home page.", is_error=True)
            return
            
        logger.info("Taking Material Image...")
        self.measurement_page.set_result_text("Taking Material Image...")
        image_data = self.camera_service.capture_image()
        
        if image_data is not None:
            self.measurement_page.set_image(image_data, "material")
            logger.info("Material Image captured and displayed.")
            self.measurement_page.set_result_text("Result...")
            self.measurement_page.set_calculation_enabled(True)
        else:
            logger.error("Failed to capture material image.")
            self.measurement_page.show_info_bar("Capture Error", "Failed to capture material image.", is_error=True)
            self.measurement_page.set_result_text("Error")