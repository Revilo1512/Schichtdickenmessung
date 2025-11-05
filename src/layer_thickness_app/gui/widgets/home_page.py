import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QFormLayout, QLabel
from PyQt6.QtGui import QPixmap
from qfluentwidgets import (
    TitleLabel, BodyLabel, SettingCardGroup, ComboBoxSettingCard,
    OptionsConfigItem, OptionsValidator, PushButton, FluentIcon,
    InfoBar, InfoBarPosition, SettingCardGroup,
    IconWidget, StrongBodyLabel, SubtitleLabel
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
        # Call update_status_display *before* auto-connect
        self.update_status_display()
        self._auto_connect_camera()

    # -----------------------------
    # UI Initialization
    # -----------------------------
    def _init_widgets(self):
        """Initialize all UI widgets."""
        
        self.title_label = SubtitleLabel("Welcome to the Layer Thickness Tool")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # --------------------------------------------------------
        
        list_html = (
            "<ul style='margin-left: 40px; line-height: 1.5em;'>"
            "<li><b>Measure:</b> Capture images and calculate layer thickness.</li>"
            "<li><b>History:</b> View, filter, and browse past measurements.</li>"
            "<li><b>Ex-/Import:</b> Export or import data.</li>"
            "<li><b>Settings:</b> Change the theme and preferences.</li>"
            "</ul>"
        )
        self.description_header_label = BodyLabel("Use the navigation panel on the left to:")
        self.description_header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.description_label = BodyLabel(list_html)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.description_label.setTextFormat(Qt.TextFormat.RichText)
        # -----------------------------------------------------

        self.image_label = QLabel(self)
        img_path = os.path.join("src", "layer_thickness_app", "gui", "resources", "measurement_device.jpg")
        pixmap = QPixmap(img_path)
        self.image_label.setPixmap(pixmap)
        self.image_label.setScaledContents(True)
        self.image_label.setFixedSize(350, 440)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # --- Camera Group ---
        self.camera_group = SettingCardGroup("Camera Status", self)

        # --- Camera Selector ---
        initial_cam_options = ["No cameras found"]
        
        self.camera_config_item = OptionsConfigItem(
            "Camera", "SelectedCamera", initial_cam_options[0], 
            OptionsValidator(initial_cam_options)
        )
        self.camera_selector_card = ComboBoxSettingCard(
            self.camera_config_item,
            FluentIcon.CAMERA,
            "Available Cameras",
            "Select a connected uEye camera",
            texts=initial_cam_options,
            parent=self.camera_group
        )

        # --- Status Widget in a titled frame ---
        self.status_widget = QFrame()
        self.status_widget.setObjectName("status_card_content")
        self.status_widget.setFrameShape(QFrame.Shape.StyledPanel)
        self.status_widget.setFrameShadow(QFrame.Shadow.Raised)
        
        main_status_layout = QVBoxLayout(self.status_widget)
        main_status_layout.setContentsMargins(15, 10, 15, 10)
        main_status_layout.setSpacing(10)

        # Title Layout (Icon + Text)
        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)
        icon_widget = IconWidget(FluentIcon.INFO, self.status_widget)
        status_title_label = StrongBodyLabel("Status Info", self.status_widget)
        
        title_layout.addWidget(icon_widget)
        title_layout.addWidget(status_title_label)
        title_layout.addStretch(1)
        
        main_status_layout.addLayout(title_layout)

        # Form Layout (Status fields)
        status_form_layout = QFormLayout()
        status_form_layout.setSpacing(10) 

        self.status_label = BodyLabel("Disconnected")
        self.status_label.setStyleSheet("font-weight: bold;")
        self.model_label = BodyLabel("N/A")
        self.resolution_label = BodyLabel("N/A")

        status_form_layout.addRow(BodyLabel("Status:"), self.status_label)
        status_form_layout.addRow(BodyLabel("Model:"), self.model_label)
        status_form_layout.addRow(BodyLabel("Resolution:"), self.resolution_label)
        
        main_status_layout.addLayout(status_form_layout)
        # --------------------------------------------------

        # --- Action Buttons in a horizontal layout ---
        self.action_button_widget = QWidget(self.camera_group)
        button_layout = QHBoxLayout(self.action_button_widget)
        button_layout.setContentsMargins(10, 5, 10, 5) 
        button_layout.setSpacing(10)

        self.refresh_button = PushButton(FluentIcon.SYNC, "Refresh List", self.action_button_widget)
        self.connect_button = PushButton(FluentIcon.PLAY, "Connect", self.action_button_widget)
        
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.connect_button)
        # ----------------------------------------------------

        # --- Add cards to group ---
        self.camera_group.addSettingCard(self.camera_selector_card)
        
        self.camera_group.vBoxLayout.addWidget(self.action_button_widget)
        self.camera_group.vBoxLayout.addWidget(self.status_widget)
        self.camera_group.vBoxLayout.addStretch(1)
        
        # ---------------------------------------------------------------

    # -----------------------------
    # Layout
    # -----------------------------
    def _init_layout(self):
        """Set up the main layout."""
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop) 
        self.main_layout.setContentsMargins(40, 40, 40, 40)
        self.main_layout.setSpacing(30) 

        # --- Left Column (Info & Image) ---
        self.left_column_widget = QWidget(self)
        left_layout = QVBoxLayout(self.left_column_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15) 

        left_layout.addWidget(self.title_label)
        left_layout.addWidget(self.image_label, 0, Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.description_header_label)
        left_layout.addWidget(self.description_label)
        left_layout.addStretch(1) # Pushes left content to the top
        
        # Create a wrapper widget for the right column ---
        self.right_column_widget = QWidget(self)
        right_layout = QVBoxLayout(self.right_column_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.camera_group)
        right_layout.addStretch(1) 
        # -----------------------------------------------------------

        # --- Add columns to main layout ---
        self.main_layout.addWidget(self.left_column_widget, 1)
        self.main_layout.addWidget(self.right_column_widget, 1)

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
            print("Attempting to auto-connect to camera...")
            first_cam_id = self.available_cameras[0]["id"]
            
            if self.camera_service.connect(first_cam_id):
                InfoBar.success(
                    title="Camera Auto-Connected",
                    content=f"Connected to {self.camera_service.get_status()['model']}.",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP
                )
            else:
                InfoBar.error(
                    title="Auto-Connect Failed",
                    content="Could not initialize the first available camera.",
                    parent=self,
                    position=InfoBarPosition.TOP
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
                position=InfoBarPosition.TOP
            )
            self.refresh_camera_list()
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
        """Update labels and button states based on the camera service's status."""
        status = self.camera_service.get_status()

        if status["connected"]:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("font-weight: bold; color: #00b050;")  # Green
            self.model_label.setText(status["model"])
            self.resolution_label.setText(f"{status['width']} x {status['height']}")
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("font-weight: bold; color: #e04141;")  # Red
            self.model_label.setText("N/A")
            self.resolution_label.setText("N/A")

        if status["connected"]:
            self.connect_button.setText("Disconnect")
            self.connect_button.setIcon(FluentIcon.PAUSE)
            
            self.refresh_button.setEnabled(False)
            self.camera_selector_card.setEnabled(False)
            self.connect_button.setEnabled(True) 
        else:
            self.connect_button.setText("Connect")
            self.connect_button.setIcon(FluentIcon.PLAY)
            
            self.refresh_button.setEnabled(True)
            is_cam_available = len(self.available_cameras) > 0
            self.camera_selector_card.setEnabled(is_cam_available)
            self.connect_button.setEnabled(is_cam_available)