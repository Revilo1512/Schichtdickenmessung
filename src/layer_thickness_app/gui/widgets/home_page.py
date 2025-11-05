from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QFormLayout
from qfluentwidgets import (
    TitleLabel, BodyLabel, SettingCardGroup, ComboBoxSettingCard,
    OptionsConfigItem, OptionsValidator, PushButton, FluentIcon,
    InfoBar, InfoBarPosition, ExpandSettingCard
)

from layer_thickness_app.services.camera_service import CameraService


class HomePage(QWidget):
    """Dashboard homepage that shows a welcome message and camera status."""

    def __init__(self, camera_service: CameraService):
        super().__init__()
        self.camera_service = camera_service
        self.available_cameras = []  # [{"id": int, "model": str}]
        
        self.setObjectName("home_page")
        self._init_widgets()
        self._init_layout()
        self._connect_signals()
        
        self.refresh_camera_list()
        self.update_status_display()

    # -----------------------------
    # UI Initialization
    # -----------------------------
    def _init_widgets(self):
        """Initialize all UI widgets."""
        self.title_label = TitleLabel("Welcome to the Layer Thickness Tool")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.description_label = BodyLabel(
            "Use the navigation panel on the left to:\n"
            "• **Measure:** Capture images and calculate layer thickness.\n"
            "• **History:** View, filter, and browse past measurements.\n"
            "• **Ex-/Import:** Export or import data.\n"
            "• **Settings:** Change the theme and preferences."
        )
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # --- Camera Group ---
        self.camera_group = SettingCardGroup("Camera Status", self)

        # --- Camera Selector ---
        # 💡 FIX: Define initial placeholder options
        initial_cam_options = ["No cameras found"]
        
        # 💡 FIX: Pass the initial options to the validator and set the first as default
        self.camera_config_item = OptionsConfigItem(
            "Camera", 
            "SelectedCamera", 
            initial_cam_options[0],  # Use first item as default
            OptionsValidator(initial_cam_options) # Pass non-empty list
        )
        self.camera_selector_card = ComboBoxSettingCard(
            self.camera_config_item,
            FluentIcon.CAMERA,
            "Available Cameras",
            "Select a connected uEye camera",
            texts=initial_cam_options,
            parent=self.camera_group
        )

        # --- Status Card ---
        self.status_widget = QFrame()
        self.status_widget.setObjectName("status_card_content")
        status_layout = QFormLayout(self.status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = BodyLabel("Disconnected")
        self.status_label.setStyleSheet("font-weight: bold;")
        self.model_label = BodyLabel("N/A")
        self.resolution_label = BodyLabel("N/A")

        status_layout.addRow(BodyLabel("Status:"), self.status_label)
        status_layout.addRow(BodyLabel("Model:"), self.model_label)
        status_layout.addRow(BodyLabel("Resolution:"), self.resolution_label)

        self.status_card = ExpandSettingCard(icon=FluentIcon.INFO, title="Device Status", parent=self.camera_group)
        self.status_card.addWidget(self.status_widget)

        # --- Button Card ---
        self.connect_button = PushButton("Connect", self)
        self.refresh_button = PushButton("Refresh List", self)

        self.button_widget_container = QWidget()
        button_layout = QVBoxLayout(self.button_widget_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.refresh_button)

        self.button_card = ExpandSettingCard(icon=FluentIcon.PLAY, title="Actions", parent=self.camera_group)
        self.button_card.addWidget(self.button_widget_container)

    # -----------------------------
    # Layout
    # -----------------------------
    def _init_layout(self):
        """Set up the main layout."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 40, 40, 40)
        self.main_layout.setSpacing(20)
        
        self.main_layout.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.description_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addStretch(1)

        # Add setting cards
        self.camera_group.addSettingCard(self.camera_selector_card)
        self.camera_group.addSettingCard(self.status_card)
        self.camera_group.addSettingCard(self.button_card)

        self.main_layout.addWidget(self.camera_group)
        self.main_layout.addStretch(2)

    # -----------------------------
    # Signals
    # -----------------------------
    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_camera_list)
        self.connect_button.clicked.connect(self.toggle_camera_connection)

    # -----------------------------
    # Camera Handling
    # -----------------------------
    def refresh_camera_list(self):
        """Fetch available cameras and update combobox."""
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
            combo.setCurrentIndex(0)  # Select the first item

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
                position=InfoBarPosition.TOP
            )
        else:
            if not self.available_cameras:
                InfoBar.error("Error", "No cameras available to connect.", parent=self, position=InfoBarPosition.TOP)
                return
                
            selected_index = self.camera_selector_card.comboBox.currentIndex()
            if selected_index < 0:
                InfoBar.error("Error", "No camera selected.", parent=self, position=InfoBarPosition.TOP)
                return
                
            selected_cam_id = self.available_cameras[selected_index]["id"]
            
            if self.camera_service.connect(selected_cam_id):
                InfoBar.success(
                    title="Camera Connected",
                    content=f"Connected to {self.camera_service.get_status()['model']}.",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP
                )
            else:
                InfoBar.error(
                    title="Connection Failed",
                    content="Could not initialize the selected camera.",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                
        self.update_status_display()

    def update_status_display(self):
        """Update labels based on the camera service's status."""
        status = self.camera_service.get_status()
        
        if status["connected"]:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("font-weight: bold; color: #00b050;")  # Green
            self.model_label.setText(status["model"])
            self.resolution_label.setText(f"{status['width']} x {status['height']}")
            self.connect_button.setText("Disconnect")
            self.camera_selector_card.setEnabled(False)
            self.refresh_button.setEnabled(False)
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("font-weight: bold; color: #e0e0e0;")  # Gray
            self.model_label.setText("N/A")
            self.resolution_label.setText("N/A")
            self.connect_button.setText("Connect")
            self.camera_selector_card.setEnabled(len(self.available_cameras) > 0)
            self.refresh_button.setEnabled(True)
