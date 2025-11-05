import os
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QStyle, QSizePolicy
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from qfluentwidgets import TitleLabel, BodyLabel, ToolButton, CaptionLabel

class SeekSlider(QSlider):
    """ A custom QSlider that allows seeking by clicking anywhere on the timeline. """
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def mousePressEvent(self, event):
        """ Jump to the position of the mouse click. """
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                event.pos().x(),
                self.width(),
            )
            self.setValue(value)


class VideoPlayer(QWidget):
    """
    A custom video player widget with integrated, theme-aware controls like a timeline,
    volume, and a play/pause button.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("video_player")

        # --- Media Player Setup ---
        self.player = QMediaPlayer()
        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)
        self._audio_output = QAudioOutput()
        self.player.setAudioOutput(self._audio_output)
        
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- Controls ---
        self.play_pause_button = ToolButton()
        self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        
        self.timeline_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)

        self.time_label = CaptionLabel("00:00 / 00:00")
        
        # --- Layout ---
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.play_pause_button)
        controls_layout.addWidget(self.timeline_slider)
        controls_layout.addWidget(self.time_label)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.video_widget)
        main_layout.addLayout(controls_layout)

        # --- Connect Signals ---
        self.play_pause_button.clicked.connect(self.toggle_playback)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.mediaStatusChanged.connect(self.update_button_icon)
        self.timeline_slider.sliderMoved.connect(self.player.setPosition)

    def set_source(self, url: QUrl):
        """Sets the video source file for the player."""
        self.player.setSource(url)

    def toggle_playback(self):
        """Plays or pauses the video depending on its current state."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self.update_button_icon()

    def update_button_icon(self):
        """Updates the play/pause button icon based on player state."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def update_position(self, position):
        """Updates the timeline slider and time label."""
        self.timeline_slider.setValue(position)
        self.update_time_label()
        
    def update_duration(self, duration):
        """Updates the timeline slider's range."""
        self.timeline_slider.setRange(0, duration)
        self.update_time_label()

    def format_time(self, ms):
        """Formats milliseconds into a MM:SS string."""
        s = round(ms / 1000)
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def update_time_label(self):
        """Updates the time label with current and total duration."""
        current_time = self.format_time(self.player.position())
        total_time = self.format_time(self.player.duration())
        self.time_label.setText(f"{current_time} / {total_time}")


class HelpPage(QWidget):
    """ Page to display an introductory video with a full-featured player. """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("help_page")
        
        # --- Widgets ---
        self.title_label = TitleLabel("Introductory Video")
        self.description_label = BodyLabel(
            "This video shows the application itself and the measuring process."
        )
        self.video_player = VideoPlayer(self)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.description_label)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.video_player)
        
        # --- Load Video File ---
        script_dir = os.path.dirname(os.path.abspath(__file__))
        gui_dir = os.path.dirname(script_dir)
        video_path = os.path.join(gui_dir, "resources", "introduction.mp4")

        if os.path.exists(video_path):
            self.video_player.set_source(QUrl.fromLocalFile(video_path))
        else:
            print(f"Warning: Video file not found at {video_path}")