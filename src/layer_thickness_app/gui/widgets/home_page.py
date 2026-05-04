"""
Dashboard homepage. Shows a welcome message, navigation hints, the
measurement-device image and the camera-status card.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QFormLayout, QLabel,
    QDoubleSpinBox,
)
from PyQt6.QtGui import QPixmap
from qfluentwidgets import (
    TitleLabel, BodyLabel, SettingCardGroup, ComboBoxSettingCard,
    OptionsConfigItem, OptionsValidator, PushButton, FluentIcon,
    InfoBar, InfoBarPosition, IconWidget, StrongBodyLabel, SubtitleLabel,
)

from layer_thickness_app.config.config import AppConfig
from layer_thickness_app.services.camera_service import CameraService
from layer_thickness_app.gui.theme import (
    card_style, status_label_style,
)

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).resolve().parent.parent
IMAGE_PATH = BASE_DIR / "resources" / "measurement_device.jpg"

_STATUS_PANEL_OBJECT_NAME   = "status_card_content"
_WELCOME_CARD_OBJECT_NAME   = "home_welcome_card"
_IMAGE_CARD_OBJECT_NAME     = "home_image_card"
_EXPOSURE_PANEL_OBJECT_NAME = "exposure_card_content"

# Default range when the camera hasn't reported its actual range yet
# (e.g. before the first connect). Real bounds replace these once the
# hardware is queried.
_EXPOSURE_DEFAULT_MIN  = 0.01
_EXPOSURE_DEFAULT_MAX  = 1000.0
_EXPOSURE_DEFAULT_STEP = 0.1


class HomePage(QWidget):
    """Dashboard homepage."""

    def __init__(self, camera_service: CameraService, config: AppConfig):
        super().__init__()
        self.camera_service = camera_service
        self.config         = config
        self.available_cameras: list[dict[str, Any]] = []

        self.setObjectName("home_page")

        self._init_layout()
        self._connect_signals()

        self.refresh_camera_list()
        self.update_status_display()
        self._auto_connect_camera()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _init_layout(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.setContentsMargins(40, 40, 40, 40)
        self.main_layout.setSpacing(40)

        self._setup_left_panel()
        self._setup_right_panel()

        self.main_layout.addWidget(self.left_column_widget,  5)
        self.main_layout.addWidget(self.right_column_widget, 4)

    def _setup_left_panel(self):
        self.left_column_widget = QWidget(self)
        left_layout = QVBoxLayout(self.left_column_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)

        # Welcome text -- wrapped in a card to match the rest of the page.
        self.text_widget = QFrame()
        self.text_widget.setObjectName(_WELCOME_CARD_OBJECT_NAME)
        self.text_widget.setStyleSheet(card_style(_WELCOME_CARD_OBJECT_NAME))
        text_layout = QVBoxLayout(self.text_widget)
        text_layout.setContentsMargins(20, 18, 20, 18)
        text_layout.setSpacing(5)

        self.title_label    = TitleLabel("Layer Thickness Tool")
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

        # Camera configuration group
        self.camera_group = SettingCardGroup("Camera Configuration", self)

        initial_cam_options = ["No cameras found"]
        self.camera_config_item = OptionsConfigItem(
            "Camera", "SelectedCamera", initial_cam_options[0],
            OptionsValidator(initial_cam_options),
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
        self.status_widget.setObjectName(_STATUS_PANEL_OBJECT_NAME)
        self.status_widget.setStyleSheet(card_style(_STATUS_PANEL_OBJECT_NAME))

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

        self.status_label     = BodyLabel("Disconnected")
        self.model_label      = BodyLabel("N/A")
        self.resolution_label = BodyLabel("N/A")

        status_form_layout.addRow(StrongBodyLabel("Connection:"),    self.status_label)
        status_form_layout.addRow(StrongBodyLabel("Device Model:"),  self.model_label)
        status_form_layout.addRow(StrongBodyLabel("Resolution:"),    self.resolution_label)
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

        # ---- Exposure card --------------------------------------------
        # Sits below the connect button. Editable only when the camera
        # is connected. Apply pushes the value to the SDK and persists
        # it via AppConfig so it's restored on the next connect.

        self.exposure_widget = QFrame()
        self.exposure_widget.setObjectName(_EXPOSURE_PANEL_OBJECT_NAME)
        self.exposure_widget.setStyleSheet(card_style(_EXPOSURE_PANEL_OBJECT_NAME))

        exp_outer = QVBoxLayout(self.exposure_widget)
        exp_outer.setContentsMargins(20, 15, 20, 15)
        exp_outer.setSpacing(10)

        exp_title = QHBoxLayout()
        exp_title.setSpacing(8)
        exp_title.addWidget(IconWidget(FluentIcon.SETTING, self.exposure_widget))
        exp_title.addWidget(StrongBodyLabel("Exposure", self.exposure_widget))
        exp_title.addStretch(1)
        exp_outer.addLayout(exp_title)

        exp_row = QHBoxLayout()
        exp_row.setSpacing(10)

        self.exposure_spinbox = QDoubleSpinBox()
        self.exposure_spinbox.setDecimals(3)
        self.exposure_spinbox.setSuffix(" ms")
        self.exposure_spinbox.setRange(_EXPOSURE_DEFAULT_MIN, _EXPOSURE_DEFAULT_MAX)
        self.exposure_spinbox.setSingleStep(_EXPOSURE_DEFAULT_STEP)
        self.exposure_spinbox.setMinimumWidth(140)

        self.exposure_apply_button = PushButton(FluentIcon.ACCEPT, "Apply")

        exp_row.addWidget(StrongBodyLabel("Exposure time:"))
        exp_row.addWidget(self.exposure_spinbox)
        exp_row.addStretch(1)
        exp_row.addWidget(self.exposure_apply_button)
        exp_outer.addLayout(exp_row)

        self.exposure_range_label = BodyLabel("Range: connect a camera first.")
        exp_outer.addWidget(self.exposure_range_label)

        # Disabled until the camera reports it's connected.
        self.exposure_spinbox.setEnabled(False)
        self.exposure_apply_button.setEnabled(False)

        self.camera_group.vBoxLayout.addSpacing(10)
        self.camera_group.vBoxLayout.addWidget(self.exposure_widget)

        left_layout.addWidget(self.text_widget)
        left_layout.addWidget(self.camera_group)
        left_layout.addStretch(1)

    def _setup_right_panel(self):
        self.right_column_widget = QWidget(self)
        right_layout = QVBoxLayout(self.right_column_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Wrap the device image in a card frame so its border matches the
        # other "boxes" on the page (welcome card, status card).
        self.image_card = QFrame(self)
        self.image_card.setObjectName(_IMAGE_CARD_OBJECT_NAME)
        self.image_card.setStyleSheet(card_style(_IMAGE_CARD_OBJECT_NAME))
        card_layout = QVBoxLayout(self.image_card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(0)

        self.image_label = QLabel()
        if IMAGE_PATH.exists():
            pixmap = QPixmap(str(IMAGE_PATH))
            scaled = pixmap.scaled(
                450, 600,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
            self.image_label.setFixedSize(scaled.size())
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.image_label.setStyleSheet("border: none; background: transparent;")
        else:
            logger.warning("Measurement device image not found at %s", IMAGE_PATH)
            self.image_label.setText("Image not found")
            self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(
            self.image_label,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        right_layout.addWidget(
            self.image_card,
            alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
        )
        right_layout.addStretch(1)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.refresh_button.clicked.connect(self.refresh_camera_list)
        self.connect_button.clicked.connect(self.toggle_camera_connection)
        self.exposure_apply_button.clicked.connect(self._on_exposure_apply_clicked)

    # ------------------------------------------------------------------
    # Camera handling
    # ------------------------------------------------------------------

    def _auto_connect_camera(self):
        if self.available_cameras and not self.camera_service.get_status()["connected"]:
            logger.info("Attempting to auto-connect to camera...")
            first_cam_id = self.available_cameras[0]["id"]

            if self.camera_service.connect(first_cam_id):
                self._after_camera_connected()
                InfoBar.success(
                    title="Camera Auto-Connected",
                    content=f"Connected to {self.camera_service.get_status()['model']}.",
                    duration=3000, parent=self, position=InfoBarPosition.TOP,
                )
            else:
                InfoBar.error(
                    title="Auto-Connect Failed",
                    content="Could not initialize the first available camera.",
                    parent=self, position=InfoBarPosition.TOP,
                )

            self.update_status_display()

    def refresh_camera_list(self):
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
        if self.camera_service.get_status()["connected"]:
            self.camera_service.disconnect()
            self._after_camera_disconnected()
            InfoBar.success(
                title="Camera Disconnected",
                content="The camera has been disconnected.",
                duration=3000, parent=self, position=InfoBarPosition.TOP,
            )
            self.refresh_camera_list()
        else:
            if not self.available_cameras:
                InfoBar.error(
                    title="Error",
                    content="No cameras available to connect.",
                    parent=self, position=InfoBarPosition.TOP,
                )
                return

            selected_index = self.camera_selector_card.comboBox.currentIndex()
            if selected_index < 0:
                InfoBar.error(
                    title="Error",
                    content="No camera selected.",
                    parent=self, position=InfoBarPosition.TOP,
                )
                return

            selected_cam_id = self.available_cameras[selected_index]["id"]

            if self.camera_service.connect(selected_cam_id):
                self._after_camera_connected()
                InfoBar.success(
                    title="Camera Connected",
                    content=f"Connected to {self.camera_service.get_status()['model']}.",
                    duration=3000, parent=self, position=InfoBarPosition.TOP,
                )
            else:
                InfoBar.error(
                    title="Connection Failed",
                    content="Could not initialize the selected camera.",
                    parent=self, position=InfoBarPosition.TOP,
                )

        self.update_status_display()

    # ------------------------------------------------------------------
    # Exposure handling
    # ------------------------------------------------------------------

    def _after_camera_connected(self) -> None:
        """
        Configure the exposure card from the live camera and re-apply
        the persisted exposure (if any).
        """
        rng = self.camera_service.get_exposure_range_ms()
        if rng is not None:
            lo, hi, inc = rng
            self.exposure_spinbox.setRange(lo, hi)
            # Smaller of the SDK increment and a user-friendly step.
            step = inc if inc > 0 else _EXPOSURE_DEFAULT_STEP
            self.exposure_spinbox.setSingleStep(step)
            self.exposure_range_label.setText(
                f"Range: {lo:.3f} – {hi:.3f} ms (step {inc:.4f} ms)"
            )
        else:
            self.exposure_range_label.setText(
                "Could not read exposure range from camera."
            )

        # Apply the persisted exposure first (if any), then reflect the
        # actual hardware value in the spinbox. If nothing is persisted,
        # just show whatever the camera defaulted to.
        saved = self.config.camera_exposure_ms
        if saved is not None:
            applied = self.camera_service.set_exposure_ms(saved)
            if applied is not None:
                logger.info(
                    "Restored persisted exposure: %.3f ms (applied %.3f ms).",
                    saved, applied,
                )

        current = self.camera_service.get_exposure_ms()
        if current is not None:
            # blockSignals isn't needed (we don't react to valueChanged)
            # but setValue can clamp; that's harmless here.
            self.exposure_spinbox.setValue(current)

        self.exposure_spinbox.setEnabled(True)
        self.exposure_apply_button.setEnabled(True)

    def _after_camera_disconnected(self) -> None:
        self.exposure_spinbox.setEnabled(False)
        self.exposure_apply_button.setEnabled(False)
        self.exposure_range_label.setText("Range: connect a camera first.")

    def _on_exposure_apply_clicked(self) -> None:
        if not self.camera_service.get_status()["connected"]:
            InfoBar.error(
                title="Camera not connected",
                content="Connect a camera before changing exposure.",
                duration=3000, parent=self, position=InfoBarPosition.TOP,
            )
            return

        requested = float(self.exposure_spinbox.value())
        applied   = self.camera_service.set_exposure_ms(requested)
        if applied is None:
            InfoBar.error(
                title="Exposure not applied",
                content="The camera rejected the requested value. "
                        "See the log for details.",
                duration=4000, parent=self, position=InfoBarPosition.TOP,
            )
            return

        # Reflect any rounding the hardware applied.
        self.exposure_spinbox.setValue(applied)
        self.config.set_camera_exposure_ms(applied)

        InfoBar.success(
            title="Exposure updated",
            content=f"Applied {applied:.3f} ms (saved).",
            duration=2500, parent=self, position=InfoBarPosition.TOP,
        )

    def update_status_display(self):
        status = self.camera_service.get_status()

        if status["connected"]:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet(status_label_style("ok"))
            self.model_label.setText(status["model"])
            self.resolution_label.setText(f"{status['width']} x {status['height']}")

            self.connect_button.setText("Disconnect")
            self.connect_button.setIcon(FluentIcon.PAUSE)

            self.refresh_button.setEnabled(False)
            self.camera_selector_card.setEnabled(False)
            self.connect_button.setEnabled(True)
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet(status_label_style("error"))
            self.model_label.setText("N/A")
            self.resolution_label.setText("N/A")

            self.connect_button.setText("Connect")
            self.connect_button.setIcon(FluentIcon.PLAY)

            self.refresh_button.setEnabled(True)
            is_cam_available = len(self.available_cameras) > 0
            self.camera_selector_card.setEnabled(is_cam_available)
            self.connect_button.setEnabled(is_cam_available)