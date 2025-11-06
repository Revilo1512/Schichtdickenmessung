import sys, os

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer

from layer_thickness_app.controller.main_controller import MainController
from layer_thickness_app.config.config import cfg
from qfluentwidgets import setTheme, isDarkTheme, Theme


# --- THEME STYLESHEETS ---
# Paths to the new QSS files
QSS_RESOURCES_PATH = "src/layer_thickness_app/gui/resources"
LIGHT_THEME_QSS = os.path.join(QSS_RESOURCES_PATH, "light_theme.qss")
DARK_THEME_QSS = os.path.join(QSS_RESOURCES_PATH, "dark_theme.qss")

class SplashWindow(QMainWindow):
    """Simple splash window with centered image."""

    def __init__(self, image_path: str):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.resize(1100, 800)

        # center the image inside a layout
        label = QLabel()
        pixmap = QPixmap(image_path)
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

def load_stylesheet(qss_file: str) -> str:
    """Helper function to read a QSS file."""
    if not os.path.exists(qss_file):
        print(f"Warning: Stylesheet file not found: {qss_file}")
        return ""
    try:
        with open(qss_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading stylesheet {qss_file}: {e}")
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
        
    print(f"Setting theme to: {actual_theme.value}") 
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
        return False  # Default to light mode on non-Windows
        
    try:
        import winreg
        # Registry path for the "app mode" theme setting
        key_path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize'
        key_name = 'AppsUseLightTheme'
        
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            # value is 0 for Dark Mode, 1 for Light Mode
            return value == 0
    except (FileNotFoundError, OSError, ImportError):
        # Key might not exist, or winreg is not available
        return False # Default to light mode

def main():
    app = QApplication(sys.argv)

    icon_path = r"src\layer_thickness_app\gui\resources\duck_icon.svg"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        print(f"Warning: Icon file not found at {icon_path}")
    
    splash = SplashWindow("src/layer_thickness_app/gui/resources/duck_icon.svg")
    splash.show()

    # force render immediately
    app.processEvents()

    # Load config and set initial theme *before* creating controller/view
    cfg.load()
    apply_app_theme(app, cfg.theme_enum)
    
    # Connect the config's theme_changed signal to our new function
    # This ensures theme changes from settings page are applied globally
    cfg.theme_changed.connect(lambda theme_enum: apply_app_theme(app, theme_enum))

    controller = MainController(config=cfg)

    # close splash manually and show main window
    def show_main():
        controller.show_window()
        splash.close()
    
    QTimer.singleShot(800, show_main)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()