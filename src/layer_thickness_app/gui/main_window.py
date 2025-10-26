import os
from PyQt6.QtGui import QIcon
from qfluentwidgets import FluentWindow, FluentIcon, setTheme, Theme

from layer_thickness_app.gui.widgets.settings_page import cfg, SettingsPage
from layer_thickness_app.gui.widgets.help_page import HelpPage
from layer_thickness_app.gui.widgets.home_page import HomePage
from layer_thickness_app.gui.widgets.history_page import HistoryPage
from layer_thickness_app.gui.widgets.csv_page import CSVPage
from layer_thickness_app.gui.widgets.measure_page import MeasurePage
from layer_thickness_app.services.database_service import DatabaseService

class MainWindow(FluentWindow):
    def __init__(self, db_service: DatabaseService):
        super().__init__()

        # Set the application title and icon
        self.setWindowTitle("Schichtdickenmessung")
        icon_path = r"src\layer_thickness_app\gui\resources\duck_icon.svg"
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"Warning: Icon file not found at {icon_path}")

        # Create instances of each page
        self.home_interface = HomePage()
        self.measure_interface = MeasurePage()
        self.history_interface = HistoryPage(db_service)
        self.csv_interface = CSVPage()
        self.help_interface = HelpPage()
        self.settings_interface = SettingsPage()

        # Add Pages to the Navigation Pane
        self.addSubInterface(self.home_interface, FluentIcon.HOME, "Home")
        self.navigationInterface.addSeparator()
        self.addSubInterface(self.measure_interface, FluentIcon.STOP_WATCH, "Measure")
        self.addSubInterface(self.history_interface, FluentIcon.HISTORY, "History")
        self.addSubInterface(self.csv_interface, FluentIcon.DOCUMENT, "Ex-/Import")
        # fixed bottom
        self.addSubInterface(self.help_interface, FluentIcon.HELP, "Help", position=1)
        self.addSubInterface(self.settings_interface, FluentIcon.SETTING, "Settings", position=1)
        
        self.resize(1100, 800)