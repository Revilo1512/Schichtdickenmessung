"""
Help and tutorial page. Plays a local tutorial video if available;
otherwise shows a placeholder card.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QSlider, QStyle,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    MULTIMEDIA_AVAILABLE = False

from layer_thickness_app.gui.theme import (
    PREVIEW_BG, PREVIEW_FG, borderless_style,
)

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).resolve().parent.parent
VIDEO_PATH = BASE_DIR / "resources" / "tutorial.mp4"

_PLACEHOLDER_OBJECT_NAME = "help_placeholder_frame"
_BUTTON_STYLE = "padding: 8px 15px; border-radius: 4px;"


class ClickableSlider(QSlider):
    """A slider that jumps exactly to the clicked position on left-click."""

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + (
                (self.maximum() - self.minimum()) * event.position().x()
            ) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))


class HelpPage(QWidget):
    """Tutorial-video page with a media player or placeholder card."""

    def __init__(self):
        super().__init__()
        self.setObjectName("helpPage")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        title_label = QLabel("Help & Tutorial")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        desc_label = QLabel(
            "Watch this tutorial to learn how to use the layer thickness "
            "measurement tool."
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("font-size: 14px; margin-bottom: 20px;")
        layout.addWidget(desc_label)

        if VIDEO_PATH.exists() and MULTIMEDIA_AVAILABLE:
            logger.info("Tutorial video found. Initializing video player.")
            self._setup_video_player(layout)
        else:
            if not VIDEO_PATH.exists():
                logger.warning("Tutorial video not found at: %s", VIDEO_PATH)
            if not MULTIMEDIA_AVAILABLE:
                logger.warning("PyQt6.QtMultimedia is not available. Cannot play video.")
            self._setup_placeholder(layout)

    def _setup_placeholder(self, layout: QVBoxLayout):
        placeholder_frame = QFrame()
        placeholder_frame.setObjectName(_PLACEHOLDER_OBJECT_NAME)
        placeholder_frame.setStyleSheet(
            f"QFrame#{_PLACEHOLDER_OBJECT_NAME} {{"
            f"  background-color: {PREVIEW_BG};"
            f"  border: 2px dashed #666;"
            f"  border-radius: 10px;"
            f"}}"
        )

        frame_layout = QVBoxLayout(placeholder_frame)

        info_label = QLabel(
            f"<b>Video Placeholder</b><br><br>"
            f"The tutorial video was not found at:<br>"
            f"<span style='color: #888;'>{VIDEO_PATH}</span><br><br>"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet(
            f"{borderless_style()} color: {PREVIEW_FG}; font-size: 14px;"
        )

        frame_layout.addWidget(info_label)
        layout.addWidget(placeholder_frame, 1)

    def _setup_video_player(self, layout: QVBoxLayout):
        self.video_widget = QVideoWidget()
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()

        self.audio_output.setVolume(0.5)
        self._apply_default_audio_device()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(str(VIDEO_PATH)))

        # Re-route audio when the OS default output device changes (e.g. user
        # plugs in headphones or switches device in Windows sound settings).
        self._media_devices = QMediaDevices(self)
        self._media_devices.audioOutputsChanged.connect(
            self._on_audio_outputs_changed
        )

        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._set_position)

        self.media_player.positionChanged.connect(self._position_changed)
        self.media_player.durationChanged.connect(self._duration_changed)

        controls_layout = QHBoxLayout()

        self.play_btn  = QPushButton()
        self.pause_btn = QPushButton()
        self.stop_btn  = QPushButton()

        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.pause_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))

        for btn in (self.play_btn, self.pause_btn, self.stop_btn):
            btn.setStyleSheet(_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.play_btn.clicked.connect(self.media_player.play)
        self.pause_btn.clicked.connect(self.media_player.pause)
        self.stop_btn.clicked.connect(self.media_player.stop)

        volume_icon = QLabel()
        volume_icon.setPixmap(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume).pixmap(18, 18)
        )

        self.volume_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._set_volume)

        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addStretch(1)
        controls_layout.addWidget(volume_icon)
        controls_layout.addWidget(self.volume_slider)

        layout.addWidget(self.video_widget, 1)
        layout.addWidget(self.position_slider)
        layout.addLayout(controls_layout)

    # ------------------------------------------------------------------
    # Slider logic
    # ------------------------------------------------------------------

    def _position_changed(self, position: int):
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(position)
        self.position_slider.blockSignals(False)

    def _duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)

    def _set_position(self, position: int):
        self.media_player.setPosition(position)

    def _set_volume(self, volume: int):
        self.audio_output.setVolume(volume / 100.0)

    # ------------------------------------------------------------------
    # Audio device follow-along
    # ------------------------------------------------------------------

    def _apply_default_audio_device(self) -> None:
        """Bind the audio output to whatever the OS currently reports as default."""
        try:
            default_device = QMediaDevices.defaultAudioOutput()
            if default_device is not None and not default_device.isNull():
                self.audio_output.setDevice(default_device)
                logger.info(
                    "Audio output bound to: %s",
                    default_device.description(),
                )
        except Exception as e:
            logger.debug("Could not bind default audio device: %s", e)

    def _on_audio_outputs_changed(self) -> None:
        """Re-apply the (possibly new) default device on hot-swap."""
        self._apply_default_audio_device()