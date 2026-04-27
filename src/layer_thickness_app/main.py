"""
Application entry point.

Sets up logging, the splash window, the theme and instantiates the
main controller. Themed Qt stylesheets are loaded from disk and
re-applied whenever ``cfg.theme_changed`` fires.
"""

from __future__ import annotations

import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer, qInstallMessageHandler, QtMsgType

from layer_thickness_app.controller.main_controller import MainController
from layer_thickness_app.config.config              import cfg
from qfluentwidgets import setTheme, Theme

# winreg is only available on Windows. Importing conditionally at module
# load keeps is_windows_dark_mode() free of per-call import overhead.
if sys.platform == "win32":
    import winreg  # noqa: F401
else:
    winreg = None  # type: ignore[assignment]


BASE_DIR       = Path(__file__).resolve().parent
RESOURCES_PATH = BASE_DIR / "gui" / "resources"

LIGHT_THEME_QSS = RESOURCES_PATH / "light_theme.qss"
DARK_THEME_QSS  = RESOURCES_PATH / "dark_theme.qss"
ICON_PATH       = RESOURCES_PATH / "icons" / "app_icon.svg"


def setup_logging():
    """
    Configure the root logger. Writes to ``app_log.txt`` with a
    1 MB × 5-backup rotation so the log doesn't grow unbounded.
    """
    rotating = RotatingFileHandler(
        "app_log.txt", maxBytes=1_048_576, backupCount=5, encoding="utf-8",
    )
    logging.basicConfig(
        level   = logging.INFO,
        format  = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            rotating,
        ],
    )


def qt_message_handler(mode, context, message):
    """Filter harmless Qt/3rd-party warnings; route the rest to the logger."""
    if "QFont::setPointSize: Point size <= 0" in message:
        return
    if mode == QtMsgType.QtWarningMsg:
        logging.warning("Qt Warning: %s", message)
    elif mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        logging.error("Qt Error: %s", message)


logger = logging.getLogger(__name__)


class SplashWindow(QMainWindow):
    """Borderless splash window shown during main-window construction."""

    def __init__(self, image_path: Path):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(1100, 800)

        label  = QLabel()
        pixmap = QPixmap(str(image_path))
        label.setPixmap(pixmap.scaled(
            300, 300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.move(screen_geometry.center() - self.rect().center())


def load_stylesheet(qss_file: Path) -> str:
    if not qss_file.exists():
        logger.warning("Stylesheet file not found: %s", qss_file)
        return ""
    try:
        return qss_file.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Error reading stylesheet %s: %s", qss_file, e)
        return ""


def apply_app_theme(app: QApplication, theme: Theme):
    if theme == Theme.AUTO:
        actual_theme = Theme.DARK if is_windows_dark_mode() else Theme.LIGHT
    else:
        actual_theme = theme

    logger.info("Setting theme to: %s", actual_theme.value)
    setTheme(actual_theme)

    stylesheet = ""
    if actual_theme == Theme.LIGHT:
        stylesheet = load_stylesheet(LIGHT_THEME_QSS)
    elif actual_theme == Theme.DARK:
        stylesheet = load_stylesheet(DARK_THEME_QSS)

    app.setStyleSheet(stylesheet)


def is_windows_dark_mode() -> bool:
    """Read 'AppsUseLightTheme' from the Windows registry. False elsewhere."""
    if winreg is None:
        return False
    try:
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        key_name = "AppsUseLightTheme"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            return value == 0
    except (FileNotFoundError, OSError):
        return False


def main():
    setup_logging()
    logger.info("Starting Layer Thickness application...")
    qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)

    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    else:
        logger.warning("Icon file not found at %s", ICON_PATH)

    splash = SplashWindow(ICON_PATH)
    splash.show()
    app.processEvents()

    # cfg auto-loads in its constructor; the initial theme can be applied
    # straight away.
    apply_app_theme(app, cfg.theme_enum)
    cfg.theme_changed.connect(lambda theme_enum: apply_app_theme(app, theme_enum))

    controller = MainController(config=cfg)

    def show_main():
        logger.info("Closing splash and showing main window.")
        controller.show_window()
        splash.close()

    def shutdown():
        logger.info("Application shutting down -- closing services.")
        try:
            controller.shutdown()
        except Exception as e:
            logger.exception("Error during shutdown: %s", e)

    app.aboutToQuit.connect(shutdown)

    QTimer.singleShot(800, show_main)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()