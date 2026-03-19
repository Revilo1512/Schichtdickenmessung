import sys
import os
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer, qInstallMessageHandler, QtMsgType

from layer_thickness_app.controller.main_controller import MainController
from layer_thickness_app.config.config import cfg
from qfluentwidgets import setTheme, Theme

# --- PATH SETUP ---
# Bestimmt den Basis-Ordner relativ zu dieser Datei (src/layer_thickness_app)
BASE_DIR = Path(__file__).resolve().parent
RESOURCES_PATH = BASE_DIR / "gui" / "resources"

LIGHT_THEME_QSS = RESOURCES_PATH / "light_theme.qss"
DARK_THEME_QSS = RESOURCES_PATH / "dark_theme.qss"
ICON_PATH = RESOURCES_PATH / "duck_icon.svg"

# --- LOGGING SETUP ---
def setup_logging():
    """Konfiguriert den Root-Logger für die gesamte App."""
    logging.basicConfig(
        level=logging.INFO, # Bei Bedarf auf logging.DEBUG für mehr Details stellen
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            # Falls du in eine Datei schreiben willst, entkommentiere die nächste Zeile:
            logging.FileHandler("app_log.txt", mode='a', encoding='utf-8')
        ]
    )

# --- QT WARNING FILTER ---
def qt_message_handler(mode, context, message):
    """Filtert harmlose Warnungen von externen Bibliotheken heraus."""
    if "QFont::setPointSize: Point size <= 0" in message:
        return  # Diese spezifische Warnung einfach ignorieren
        
    # Alle anderen Qt-internen Warnungen an unseren Logger weiterleiten
    if mode == QtMsgType.QtWarningMsg:
        logging.warning("Qt Warning: %s", message)
    elif mode == QtMsgType.QtCriticalMsg or mode == QtMsgType.QtFatalMsg:
        logging.error("Qt Error: %s", message)

logger = logging.getLogger(__name__)

class SplashWindow(QMainWindow):
    """Simple splash window with centered image."""

    def __init__(self, image_path: Path):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.resize(1100, 800)

        # center the image inside a layout
        label = QLabel()
        pixmap = QPixmap(str(image_path))
        label.setPixmap(pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # center window on screen
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.move(screen_geometry.center() - self.rect().center())

def load_stylesheet(qss_file: Path) -> str:
    """Helper function to read a QSS file."""
    if not qss_file.exists():
        logger.warning("Stylesheet file not found: %s", qss_file)
        return ""
    try:
        with open(qss_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error("Error reading stylesheet %s: %s", qss_file, e)
        return ""

def apply_app_theme(app: QApplication, theme: Theme):
    """
    Applies the full theme (Fluent and custom QSS) to the application.
    """
    stylesheet = ""

    if theme == Theme.AUTO:
        actual_theme = Theme.DARK if is_windows_dark_mode() else Theme.LIGHT
    else:
        actual_theme = theme
        
    logger.info("Setting theme to: %s", actual_theme.value) 
    setTheme(actual_theme)
    
    if actual_theme == Theme.LIGHT:
        stylesheet = load_stylesheet(LIGHT_THEME_QSS)
    elif actual_theme == Theme.DARK:
        stylesheet = load_stylesheet(DARK_THEME_QSS)
    
    app.setStyleSheet(stylesheet)

def is_windows_dark_mode() -> bool:
    """
    Checks the Windows Registry for the "AppsUseLightTheme" setting.
    Returns True if dark mode is enabled, False if light mode.
    Defaults to False (light mode) if the key is not found or on non-Windows OS.
    """
    if sys.platform != 'win32':
        return False  
        
    try:
        import winreg
        key_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize'
        key_name = 'AppsUseLightTheme'
        
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            return value == 0
    except (FileNotFoundError, OSError, ImportError):
        return False

def main():
    # 1. Logging initialisieren, bevor irgendetwas anderes passiert
    setup_logging()
    logger.info("Starting Schichtdickenmessung application...")
    qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)

    # 2. Icon laden (jetzt mit sicherem pathlib-Pfad)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    else:
        logger.warning("Icon file not found at %s", ICON_PATH)
    
    splash = SplashWindow(ICON_PATH)
    splash.show()

    # force render immediately
    app.processEvents()

    # Load config and set initial theme *before* creating controller/view
    cfg.load()
    apply_app_theme(app, cfg.theme_enum)
    
    cfg.theme_changed.connect(lambda theme_enum: apply_app_theme(app, theme_enum))

    controller = MainController(config=cfg)

    def show_main():
        logger.info("Closing splash and showing main window.")
        controller.show_window()
        splash.close()
    
    QTimer.singleShot(800, show_main)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()