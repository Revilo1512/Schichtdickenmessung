import os
import sys
from PyQt6.QtCore import (
    QUrl, Qt, QObject, QThread, pyqtSignal, pyqtSlot, QStandardPaths
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSlider, QStyle, 
    QSizePolicy, QProgressBar, QApplication, QStackedWidget
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from qfluentwidgets import TitleLabel, BodyLabel, ToolButton, CaptionLabel
from pytubefix import YouTube


class VideoDownloader(QObject):
    """
    Runs on a separate thread to download a YouTube video without
    blocking the main UI.
    """
    # Signal: (current_percentage)
    progress = pyqtSignal(int)
    # Signal: (file_path_to_video)
    finished = pyqtSignal(str)
    # Signal: (error_message)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_size = 0

    def _progress_callback(self, stream, chunk, bytes_remaining):
        """Pytube's progress callback."""
        if self._total_size == 0:
            self._total_size = stream.filesize
        
        bytes_downloaded = self._total_size - bytes_remaining
        percentage = (bytes_downloaded / self._total_size) * 100
        self.progress.emit(int(percentage))

    @pyqtSlot(str, str)
    def download(self, url: str, save_path: str):
        """
        Downloads the video from 'url' and saves it to 'save_path'.
        """
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Setup YouTube object with progress callback
            yt = YouTube(url, on_progress_callback=self._progress_callback)
            
            # Get the best progressive stream (video + audio)
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            
            if not stream:
                self.error.emit("No suitable MP4 stream found.")
                return

            self._total_size = stream.filesize
            
            stream.download(
                output_path=os.path.dirname(save_path),
                filename=os.path.basename(save_path)
            )
            
            # Signal completion
            self.finished.emit(save_path)

        except Exception as e:
            self.error.emit(f"Download failed: {str(e)}")


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
    """ 
    Page to display an introductory video.
    Checks for a local copy, downloads from YouTube if missing,
    and displays a progress bar during download.
    """
    
    # -----------------------------------------------------------
    # SET VIDEO URL AND FILE DETAILS HERE 
    # -----------------------------------------------------------
    VIDEO_URL = "https://www.youtube.com/watch?v=w8a6-tIsIgw"
    VIDEO_FILENAME = "introduction.mp4"
    # -----------------------------------------------------------

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("help_page")
        
        # --- Video Path Setup ---
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Fallback to a standard app data location
        try:
            gui_dir = os.path.dirname(script_dir)
            self.video_folder = os.path.join(gui_dir, "resources")
        except Exception:
            # A more robust fallback: use the app's standard data location
            self.video_folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            os.makedirs(self.video_folder, exist_ok=True)

        self.video_path = os.path.join(self.video_folder, self.VIDEO_FILENAME)
        
        # Thread for the downloader
        self.download_thread = None
        
        # --- Widgets ---
        self.title_label = TitleLabel("Introductory Video")
        self.description_label = BodyLabel(
            "This video shows the application itself and the measuring process."
        )
        
        # --- Stacked Widget for Player/Loading ---
        # This widget will switch between the loading bar and the video player
        self.view_stack = QStackedWidget(self)
        
        # 1. Loading Widget
        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label = CaptionLabel("Checking for video file...")
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 100)
        self.loading_bar.setTextVisible(True)
        loading_layout.addStretch(1)
        loading_layout.addWidget(self.loading_label, 0, Qt.AlignmentFlag.AlignCenter)
        loading_layout.addSpacing(10)
        loading_layout.addWidget(self.loading_bar)
        loading_layout.addStretch(1)
        
        # 2. Video Player Widget
        self.video_player = VideoPlayer(self)

        self.view_stack.addWidget(self.loading_widget) # Index 0
        self.view_stack.addWidget(self.video_player)   # Index 1

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.description_label)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.view_stack) # Add the stack instead of the player
        
        # --- Check for Video and Load ---
        self.check_and_load_video()

    def check_and_load_video(self):
        """
        Checks if the video file exists. If yes, loads it.
        If not, starts the download process.
        """
        if os.path.exists(self.video_path):
            self.load_video(self.video_path)
        else:
            print(f"Video not found at {self.video_path}. Starting download...")
            self.start_download()

    def load_video(self, file_path):
        """Loads the video into the player and shows it."""
        self.video_player.set_source(QUrl.fromLocalFile(file_path))
        self.view_stack.setCurrentWidget(self.video_player)

    def start_download(self):
        """
        Initializes the downloader worker and thread
        and connects all signals.
        """
        # Show the loading widget
        self.view_stack.setCurrentWidget(self.loading_widget)
        self.loading_label.setText(f"Downloading video from YouTube...")

        # Setup thread and worker
        self.download_thread = QThread(self)
        self.downloader = VideoDownloader()
        self.downloader.moveToThread(self.download_thread)

        # Connect signals
        self.downloader.progress.connect(self.on_download_progress)
        self.downloader.finished.connect(self.on_download_finished)
        self.downloader.error.connect(self.on_download_error)
        
        # Start the thread and tell the worker to download
        self.download_thread.started.connect(
            lambda: self.downloader.download(self.VIDEO_URL, self.video_path)
        )
        
        # Clean up the thread when the worker is done
        self.downloader.finished.connect(self.download_thread.quit)
        self.downloader.finished.connect(self.downloader.deleteLater)
        self.download_thread.finished.connect(self.download_thread.deleteLater)

        # Start the download
        self.download_thread.start()

    @pyqtSlot(int)
    def on_download_progress(self, percentage):
        """Updates the progress bar."""
        self.loading_bar.setValue(percentage)

    @pyqtSlot(str)
    def on_download_finished(self, file_path):
        """Called when download is successful."""
        print(f"Video downloaded successfully to {file_path}")
        self.loading_label.setText("Download complete. Loading video...")
        self.load_video(file_path)

    @pyqtSlot(str)
    def on_download_error(self, error_msg):
        """Called if the download fails."""
        print(f"Error downloading video: {error_msg}")
        self.loading_label.setText(f"Error: {error_msg}")
        self.loading_bar.hide()

