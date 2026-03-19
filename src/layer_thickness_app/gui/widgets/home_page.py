import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QFormLayout,
    QLabel,
)
from PyQt6.QtGui import QPixmap
from qfluentwidgets import (
    TitleLabel,
    BodyLabel,
    SettingCardGroup,
    ComboBoxSettingCard,
    OptionsConfigItem,
    OptionsValidator,
    PushButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    IconWidget,
    StrongBodyLabel,
    SubtitleLabel,
)

from layer_thickness_app.services.camera_service import CameraService

logger = logging.getLogger(__name__)

# --- PATH SETUP ---
BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_PATH = BASE_DIR / "resources" / "measurement_device.jpg"

class HomePage(QWidget):
    """Dashboard homepage that shows a welcome message and camera status."""

    def __init__(self, camera_service: CameraService):
        super().__init__()
        self.camera_service = camera_service
        self.available_cameras: list[dict[str, Any]] = []

        self.setObjectName("home_page")
        
        self._init_layout()
        self._connect_signals()

        self.refresh_camera_list()
        self.update_status_display()
        self._auto_connect_camera()

    # -----------------------------
    # UI Initialization & Layout
    # -----------------------------
    def _init_layout(self):
        """Set up the main layout and initialize widgets."""
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(40, 40, 40, 40)
        self.main_layout.setSpacing(40)

        # Build the two main columns
        self._setup_left_panel()
        self._setup_right_panel()

        self.main_layout.addWidget(self.left_column_widget, 5)
        self.main_layout.addWidget(self.right_column_widget, 4)

    def _setup_left_panel(self):
        """Builds the left side of the dashboard (Text Info & Camera Settings)."""
        self.left_column_widget = QWidget(self)
        left_layout = QVBoxLayout(self.left_column_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(40) 

        # ---------------------------------------------------
        # 1. Text Info
        # ---------------------------------------------------
        self.text_widget = QWidget()
        text_layout = QVBoxLayout(self.text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(5)

        self.title_label = TitleLabel("Layer Thickness Tool")
        self.subtitle_label = SubtitleLabel("Welcome to the dashboard")
        
        list_html = (
            "<div style='line-height: 1.8em; font-size: 15px; margin-top: 15px;'>"
            "<p>Use the navigation panel on the left to:</p>"
            "<p style='margin-left: 5px;'>"
            "&bull; &nbsp;<b>Measure:</b> Capture images and calculate layer thickness.<br>"
            "&bull; &nbsp;<b>History:</b> View, filter, and browse past measurements.<br>"
            "&bull; &nbsp;<b>Ex-/Import:</b> Export or import data to CSV.<br>"
            "&bull; &nbsp;<b>Settings:</b> Change the theme and preferences."
            "</p>"
            "</div>"
        )
        self.description_label = BodyLabel(list_html)
        self.description_label.setTextFormat(Qt.TextFormat.RichText)
        self.description_label.setWordWrap(True)

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)
        text_layout.addWidget(self.description_label)

        # ---------------------------------------------------
        # 2. Camera Configuration Group (Bottom Left)
        # ---------------------------------------------------
        self.camera_group = SettingCardGroup("Camera Configuration", self)

        initial_cam_options = ["No cameras found"]
        self.camera_config_item = OptionsConfigItem(
            "Camera", "SelectedCamera", initial_cam_options[0], OptionsValidator(initial_cam_options)
        )
        self.camera_selector_card = ComboBoxSettingCard(
            self.camera_config_item,
            FluentIcon.CAMERA,
            "Available Cameras",
            "Select a connected uEye camera",
            texts=initial_cam_options,
            parent=self.camera_group,
        )

        self.status_widget = QFrame()
        self.status_widget.setObjectName("status_card_content")
        self.status_widget.setStyleSheet("""
            QFrame#status_card_content {
                background-color: transparent;
                border: 1px solid rgba(128, 128, 128, 0.25);
                border-radius: 8px;
            }
        """)

        main_status_layout = QVBoxLayout(self.status_widget)
        main_status_layout.setContentsMargins(20, 15, 20, 15)
        main_status_layout.setSpacing(15)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)
        title_layout.addWidget(IconWidget(FluentIcon.INFO, self.status_widget))
        title_layout.addWidget(StrongBodyLabel("Status Information", self.status_widget))
        title_layout.addStretch(1)
        main_status_layout.addLayout(title_layout)

        status_form_layout = QFormLayout()
        status_form_layout.setSpacing(12)
        
        self.status_label = BodyLabel("Disconnected")
        self.model_label = BodyLabel("N/A")
        self.resolution_label = BodyLabel("N/A")

        status_form_layout.addRow(StrongBodyLabel("Connection:"), self.status_label)
        status_form_layout.addRow(StrongBodyLabel("Device Model:"), self.model_label)
        status_form_layout.addRow(StrongBodyLabel("Resolution:"), self.resolution_label)
        main_status_layout.addLayout(status_form_layout)

        self.action_button_widget = QWidget()
        button_layout = QHBoxLayout(self.action_button_widget)
        button_layout.setContentsMargins(0, 10, 0, 0)
        button_layout.setSpacing(15)

        self.refresh_button = PushButton(FluentIcon.SYNC, "Refresh List")
        self.connect_button = PushButton(FluentIcon.PLAY, "Connect")

        button_layout.addStretch(1) 
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.connect_button)

        self.camera_group.addSettingCard(self.camera_selector_card)
        self.camera_group.vBoxLayout.addSpacing(10)
        self.camera_group.vBoxLayout.addWidget(self.status_widget)
        self.camera_group.vBoxLayout.addWidget(self.action_button_widget)

        left_layout.addWidget(self.text_widget)
        left_layout.addWidget(self.camera_group)
        left_layout.addStretch(1) 

    def _setup_right_panel(self):
        """Builds the right side of the dashboard (Image)."""
        self.right_column_widget = QWidget(self)
        right_layout = QVBoxLayout(self.right_column_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(self)
        if IMAGE_PATH.exists():
            pixmap = QPixmap(str(IMAGE_PATH))
            
            scaled_pixmap = pixmap.scaled(
                450, 600, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setFixedSize(scaled_pixmap.size())
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.image_label.setStyleSheet("border-radius: 12px; border: 1px solid rgba(128, 128, 128, 0.2);")
        else:
            logger.warning("Measurement device image not found at %s", IMAGE_PATH)
            self.image_label.setText("Image not found")
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        right_layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        right_layout.addStretch(1)

    # -----------------------------
    # Signals
    # -----------------------------
    def _connect_signals(self):
        """Connect signals to slots."""
        self.refresh_button.clicked.connect(self.refresh_camera_list)
        self.connect_button.clicked.connect(self.toggle_camera_connection)

    # -----------------------------
    # Camera Handling
    # -----------------------------
    def _auto_connect_camera(self):
        """Attempts to connect to the first available camera on startup."""
        if self.available_cameras and not self.camera_service.get_status()["connected"]:
            logger.info("Attempting to auto-connect to camera...")
            first_cam_id = self.available_cameras[0]["id"]

            if self.camera_service.connect(first_cam_id):
                InfoBar.success(
                    title="Camera Auto-Connected",
                    content=f"Connected to {self.camera_service.get_status()['model']}.",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            else:
                InfoBar.error(
                    title="Auto-Connect Failed",
                    content="Could not initialize the first available camera.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )

            self.update_status_display()

    def refresh_camera_list(self):
        """Fetch available cameras and update combobox."""
        if self.camera_service.get_status()["connected"]:
            return

        self.available_cameras = self.camera_service.list_available_cameras()

        combo = self.camera_selector_card.comboBox
        combo.clear()

        if not self.available_cameras:
            combo.addItem("No cameras found")
            combo.setEnabled(False)
            self.connect_button.setEnabled(False)
        else:
            cam_names = [f"ID {cam['id']}: {cam['model']}" for cam in self.available_cameras]
            combo.addItems(cam_names)
            combo.setEnabled(True)
            self.connect_button.setEnabled(True)
            combo.setCurrentIndex(0)

        self.update_status_display()

    def toggle_camera_connection(self):
        """Connects or disconnects the selected camera."""
        if self.camera_service.get_status()["connected"]:
            self.camera_service.disconnect()
            InfoBar.success(
                title="Camera Disconnected",
                content="The camera has been disconnected.",
                duration=3000,
                parent=self,
                position=InfoBarPosition.TOP,
            )
            self.refresh_camera_list()
        else:
            if not self.available_cameras:
                InfoBar.error(
                    title="Error",
                    content="No cameras available to connect.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return

            selected_index = self.camera_selector_card.comboBox.currentIndex()
            if selected_index < 0:
                InfoBar.error(
                    title="Error",
                    content="No camera selected.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return

            selected_cam_id = self.available_cameras[selected_index]["id"]

            if self.camera_service.connect(selected_cam_id):
                InfoBar.success(
                    title="Camera Connected",
                    content=f"Connected to {self.camera_service.get_status()['model']}.",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
            else:
                InfoBar.error(
                    title="Connection Failed",
                    content="Could not initialize the selected camera.",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )

        self.update_status_display()

    def update_status_display(self):
        """Update labels and button states based on the camera service's status."""
        status = self.camera_service.get_status()

        if status["connected"]:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("font-weight: bold; color: #00b050;")  # Green
            self.model_label.setText(status["model"])
            self.resolution_label.setText(f"{status['width']} x {status['height']}")
            
            self.connect_button.setText("Disconnect")
            self.connect_button.setIcon(FluentIcon.PAUSE)

            self.refresh_button.setEnabled(False)
            self.camera_selector_card.setEnabled(False)
            self.connect_button.setEnabled(True)
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("font-weight: bold; color: #e04141;")  # Red
            self.model_label.setText("N/A")
            self.resolution_label.setText("N/A")
            
            self.connect_button.setText("Connect")
            self.connect_button.setIcon(FluentIcon.PLAY)

            self.refresh_button.setEnabled(True)
            is_cam_available = len(self.available_cameras) > 0
            self.camera_selector_card.setEnabled(is_cam_available)
            self.connect_button.setEnabled(is_cam_available)