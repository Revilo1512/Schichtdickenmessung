from __future__ import annotations

from PyQt6.QtCore import QSize
from qfluentwidgets import FluentWindow, FluentIcon

from layer_thickness_app.config.config                import AppConfig
from layer_thickness_app.gui.widgets.settings_page    import SettingsPage
from layer_thickness_app.gui.widgets.help_page        import HelpPage
from layer_thickness_app.gui.widgets.home_page        import HomePage
from layer_thickness_app.gui.widgets.history_page     import HistoryPage
from layer_thickness_app.gui.widgets.csv_page         import CSVPage
from layer_thickness_app.gui.widgets.measure_page     import MeasurePage
from layer_thickness_app.gui.widgets.calibration_page import CalibrationPage
from layer_thickness_app.gui.widgets.validation_page  import ValidationPage

from layer_thickness_app.services.database_service    import DatabaseService
from layer_thickness_app.services.import_service      import ImportService
from layer_thickness_app.services.export_service      import ExportService
from layer_thickness_app.services.camera_service      import CameraService
from layer_thickness_app.services.calibration_service import CalibrationService
from layer_thickness_app.services.msa_service         import MSAService


class MainWindow(FluentWindow):
    """Main application window with the Fluent-style navigation pane."""

    def __init__(
        self,
        db_service:          DatabaseService,
        import_service:      ImportService,
        export_service:      ExportService,
        camera_service:      CameraService,
        calibration_service: CalibrationService,
        msa_service:         MSAService,
        config:              AppConfig,
    ):
        super().__init__()
        self.config = config
        self.setWindowTitle("Schichtdickenmessung")

        # ---- Pages ----------------------------------------------------
        self.home_interface        = HomePage(camera_service)
        self.measure_interface     = MeasurePage()
        self.history_interface     = HistoryPage(db_service)
        self.calibration_interface = CalibrationPage(db_service, calibration_service)
        self.validation_interface  = ValidationPage(
            db_service, calibration_service, msa_service,
        )
        self.csv_interface         = CSVPage(db_service, import_service, export_service)
        self.help_interface        = HelpPage()
        self.settings_interface    = SettingsPage(config=self.config)

        # ---- Navigation pane -----------------------------------------
        self.addSubInterface(self.home_interface, FluentIcon.HOME, "Home")
        self.navigationInterface.addSeparator()

        self.addSubInterface(self.measure_interface, FluentIcon.STOP_WATCH, "Measure")
        self.addSubInterface(self.history_interface, FluentIcon.HISTORY,    "History")
        self.navigationInterface.addSeparator()

        # Testing cluster
        self.addSubInterface(self.calibration_interface, FluentIcon.IOT,         "Calibration")
        self.addSubInterface(self.validation_interface,  FluentIcon.CERTIFICATE, "Validation")
        self.navigationInterface.addSeparator()

        self.addSubInterface(self.csv_interface,     FluentIcon.DOCUMENT, "Ex-/Import")
        self.addSubInterface(self.help_interface,     FluentIcon.HELP,    "Help",     position=1)
        self.addSubInterface(self.settings_interface, FluentIcon.SETTING, "Settings", position=1)

        # ---- Config signals ------------------------------------------
        self.config.window_size_changed.connect(self.apply_window_size)
        # Apply persisted size (also sets initial geometry on first run).
        self.apply_window_size(self.config.window_size)

    def apply_window_size(self, size_str: str):
        """Apply the window size specified by AppConfig."""
        max_size = QSize(16777215, 16777215)
        self.setMaximumSize(max_size)
        self.setMinimumSize(0, 0)
        self.showNormal()

        if size_str == "Fullscreen":
            self.showFullScreen()
            return

        if "x" in size_str:
            try:
                w, h = map(int, size_str.split("x"))
                self.setFixedSize(w, h)
                self.move_to_center()
                return
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Invalid window size in config: %s. Error: %s", size_str, e,
                )

        self.setFixedSize(1100, 800)
        self.move_to_center()

    def move_to_center(self):
        if self.screen():
            screen_geo = self.screen().availableGeometry()
            self.move(screen_geo.center() - self.rect().center())