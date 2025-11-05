import os
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QSize
from qfluentwidgets import FluentWindow, FluentIcon, setTheme, Theme

from layer_thickness_app.config.config import AppConfig
from layer_thickness_app.gui.widgets.settings_page import SettingsPage
from layer_thickness_app.gui.widgets.help_page import HelpPage
from layer_thickness_app.gui.widgets.home_page import HomePage
from layer_thickness_app.gui.widgets.history_page import HistoryPage
from layer_thickness_app.gui.widgets.csv_page import CSVPage
from layer_thickness_app.gui.widgets.measure_page import MeasurePage
from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.import_service import ImportService
from layer_thickness_app.services.export_service import ExportService
from layer_thickness_app.services.camera_service import CameraService # Import CameraService

class MainWindow(FluentWindow):
    def __init__(self, 
                 db_service: DatabaseService, 
                 import_service: ImportService, 
                 export_service: ExportService,
                 camera_service: CameraService, # Add camera_service
                 config: AppConfig):
        super().__init__()
        self.config = config

        # Set the application title and icon
        self.setWindowTitle("Schichtdickenmessung")
        icon_path = r"src\layer_thickness_app\gui\resources\duck_icon.svg"
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"Warning: Icon file not found at {icon_path}")

        # Create instances of each page
        self.home_interface = HomePage(camera_service) # Pass service to HomePage
        self.measure_interface = MeasurePage()
        self.history_interface = HistoryPage(db_service)
        # Pass services to CSVPage
        self.csv_interface = CSVPage(db_service, import_service, export_service) 
        self.help_interface = HelpPage()
        # Pass config to SettingsPage
        self.settings_interface = SettingsPage(config=self.config) 

        # Add Pages to the Navigation Pane
        self.addSubInterface(self.home_interface, FluentIcon.HOME, "Home")
        self.navigationInterface.addSeparator()
        self.addSubInterface(self.measure_interface, FluentIcon.STOP_WATCH, "Measure")
        self.addSubInterface(self.history_interface, FluentIcon.HISTORY, "History")
        self.addSubInterface(self.csv_interface, FluentIcon.DOCUMENT, "Ex-/Import")
        # fixed bottom
        self.addSubInterface(self.help_interface, FluentIcon.HELP, "Help", position=1)
        self.addSubInterface(self.settings_interface, FluentIcon.SETTING, "Settings", position=1)
        
        # Connect config signals
        self.config.window_size_changed.connect(self.apply_window_size)
        
        # Set initial size and make it fixed
        initial_w, initial_h = 1100, 800
        self.setFixedSize(initial_w, initial_h)
        
        # Apply initial window size from config *after* default size is set
        self.apply_window_size(self.config.window_size)

    def apply_window_size(self, size_str: str):
        """Applies the window size from the config and makes it fixed."""
        
        # Unset fixed size before changes
        max_size = QSize(16777215, 16777215)
        self.setMaximumSize(max_size)
        self.setMinimumSize(0, 0)
        
        self.showNormal() # Exit fullscreen if active
        
        if size_str == "Fullscreen":
            # Fullscreen doesn't use setFixedSize
            self.showFullScreen()
        elif "x" in size_str:
            try:
                w, h = map(int, size_str.split('x'))
                self.setFixedSize(w, h)
                self.move_to_center()
            except Exception as e:
                print(f"Invalid window size in config: {size_str}. Error: {e}")
                self.setFixedSize(1100, 800)
                self.move_to_center()
        else:
            self.setFixedSize(1100, 800)
            self.move_to_center()

    def move_to_center(self):
        """Moves the window to the center of the available screen."""
        if self.screen():
            screen_geo = self.screen().availableGeometry()
            self.move(screen_geo.center() - self.rect().center())