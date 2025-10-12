# import gui
from layer_thickness_app.gui.main_window import MainWindow

# import all services
from layer_thickness_app.services.camera_service import CameraService
from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.material_service import MaterialService
from layer_thickness_app.services.calculation_service import CalculationService
from layer_thickness_app.services.export_service import ExportService
from layer_thickness_app.services.import_service import ImportService

class MainController:
    """
    The central controller that manages the GUI and services.
    """
    def __init__(self):
        # The controller "owns" all the major objects in the application.
        self.view = MainWindow()
        self.camera_service = CameraService()
        self.db_service = DatabaseService("data/measurements.db")
        self.material_service = MaterialService()
        self.calculation_service = CalculationService()
        self.export_service = ExportService(self.db_service)
        self.import_service = ImportService(self.db_service)

        # Store the view's pages for easy access
        self.measurement_page = self.view.measure_interface
        
        # This is the core of the controller's logic. It tells the application
        # what to do when the user interacts with the GUI.
        self._connect_signals()

    def show_window(self):
        """Makes the main window visible."""
        self.view.show()

    def _connect_signals(self):
        """Connects all the UI signals to the controller's methods."""
        # Get the 'Start Measurement' button from the measurement page and connect its
        # 'clicked' signal to the 'on_start_measurement' method.
        #self.measurement_page.measure_button.clicked.connect(self.on_start_measurement)
        
        # You would connect other signals here, for example:
        # self.view.export_button.clicked.connect(self.on_export_data)
        # self.view.material_dropdown.currentTextChanged.connect(self.on_material_selected)
        pass
    # --- 4. Define the methods (slots) that handle the logic ---
    
    def on_start_measurement(self):
        """
        This method is triggered when the user clicks the 'Start Measurement' button.
        It orchestrates the entire measurement process.
        """
        print("Controller: Received start measurement signal.")
        
        try:
            # Step A: Get data from services
            # In a real app, you'd get the selected material from the GUI
            material_id = "sio2" 
            material_properties = self.material_service.get_material_by_id(material_id)
            if not material_properties:
                self.measurement_page.result_label.setText("Error: Material not found.")
                return

            # Step B: Interact with hardware via a service
            image_data = self.camera_service.capture_image()
            if image_data is None:
                self.measurement_page.result_label.setText("Error: Failed to capture image.")
                return

            # Step C: Perform calculations via a service
            thickness = self.calculation_service.calculate_thickness(image_data, material_properties)

            # Step D: Save results via a service
            self.db_service.save_measurement(material_id, thickness)
            print(f"Controller: Saved measurement to DB: {thickness} nm")

            # Step E: Update the View with the final result
            self.measurement_page.result_label.setText(f"Measured Thickness: <b>{thickness:.2f} nm</b>")

        except Exception as e:
            # Handle potential errors from any of the services
            print(f"Controller: An error occurred - {e}")
            self.measurement_page.result_label.setText(f"Error: {e}")