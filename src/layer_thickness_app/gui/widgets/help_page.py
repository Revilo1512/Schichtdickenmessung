import logging
from pathlib import Path

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                             QHBoxLayout, QFrame, QSlider, QStyle)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont

# Check if PyQt6 Multimedia is installed
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    MULTIMEDIA_AVAILABLE = False

logger = logging.getLogger(__name__)

# Local path to the video (relative to this file)
BASE_DIR = Path(__file__).resolve().parent.parent
VIDEO_PATH = BASE_DIR / "resources" / "tutorial.mp4"

class ClickableSlider(QSlider):
    """A custom slider that jumps exactly to the clicked position."""
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate the exact value based on the mouse click coordinates
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))

class HelpPage(QWidget):
    """
    Help page that displays a tutorial video if it exists locally.
    If the video is missing, a placeholder is displayed instead.
    Contains a fully functional media player with seek and volume sliders.
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("helpPage")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # --- Title ---
        title_label = QLabel("Help & Tutorial")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # --- Description ---
        desc_label = QLabel("Watch this tutorial to learn how to use the layer thickness measurement tool.")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("font-size: 14px; margin-bottom: 20px;")
        layout.addWidget(desc_label)

        # --- Video Player OR Placeholder ---
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
        """Creates a nice placeholder box while the video is missing."""
        placeholder_frame = QFrame()
        placeholder_frame.setStyleSheet("""
            QFrame {
                background-color: #2E2E2E; 
                border: 2px dashed #666; 
                border-radius: 10px;
            }
        """)
        
        frame_layout = QVBoxLayout(placeholder_frame)
        
        info_label = QLabel(f"<b>Video Placeholder</b><br><br>"
                            f"The tutorial video was not found at:<br>"
                            f"<span style='color: #888;'>{VIDEO_PATH}</span><br><br>")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: white; font-size: 14px; border: none;")
        
        frame_layout.addWidget(info_label)
        layout.addWidget(placeholder_frame, 1) # stretch

    def _setup_video_player(self, layout: QVBoxLayout):
        """Initializes the PyQt6 video player with seek slider, volume, and icons."""
        self.video_widget = QVideoWidget()
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        
        # Start volume at 50%
        self.audio_output.setVolume(0.5)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl.fromLocalFile(str(VIDEO_PATH)))
        
        # --- Clickable Seek Slider ---
        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._set_position)
        
        self.media_player.positionChanged.connect(self._position_changed)
        self.media_player.durationChanged.connect(self._duration_changed)

        # --- Controls Layout ---
        controls_layout = QHBoxLayout()
        
        # 1. Playback Buttons
        self.play_btn = QPushButton()
        self.pause_btn = QPushButton()
        self.stop_btn = QPushButton()
        
        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.pause_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.stop_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        
        button_style = "padding: 8px 15px; border-radius: 4px;"
        for btn in [self.play_btn, self.pause_btn, self.stop_btn]:
            btn.setStyleSheet(button_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.play_btn.clicked.connect(self.media_player.play)
        self.pause_btn.clicked.connect(self.media_player.pause)
        self.stop_btn.clicked.connect(self.media_player.stop)

        # 2. Volume Control
        volume_icon = QLabel()
        volume_icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume).pixmap(18, 18))
        
        self.volume_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50) # Matches the 0.5 audio output set above
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._set_volume)
        
        # Assemble controls horizontally
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addStretch(1) # Pushes the volume controls to the right side
        controls_layout.addWidget(volume_icon)
        controls_layout.addWidget(self.volume_slider)
        
        layout.addWidget(self.video_widget, 1) # Stretch
        layout.addWidget(self.position_slider)
        layout.addLayout(controls_layout)

    # --- Slider Logic ---
    def _position_changed(self, position: int):
        """Updates the slider when the video plays."""
        self.position_slider.blockSignals(True) # Prevent infinite feedback loop
        self.position_slider.setValue(position)
        self.position_slider.blockSignals(False)

    def _duration_changed(self, duration: int):
        """Sets the slider range based on the length of the loaded video."""
        self.position_slider.setRange(0, duration)

    def _set_position(self, position: int):
        """Seeks the video when the user drags or clicks the position slider."""
        self.media_player.setPosition(position)

    def _set_volume(self, volume: int):
        """Adjusts the volume (Qt6 requires a float between 0.0 and 1.0)"""
        self.audio_output.setVolume(volume / 100.0)