import sys, os

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer

from layer_thickness_app.controller.main_controller import MainController
from layer_thickness_app.config.config import cfg
from qfluentwidgets import setTheme, qconfig, Theme

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
    # 1. Set Fluent theme
    setTheme(theme)
    
    # 2. Load custom QSS
    if theme == Theme.LIGHT:
        stylesheet = load_stylesheet(LIGHT_THEME_QSS)
    elif theme == Theme.DARK:
        stylesheet = load_stylesheet(DARK_THEME_QSS)
    
    # 3. Apply custom QSS to the whole application
    app.setStyleSheet(stylesheet)


def main():
    app = QApplication(sys.argv)
    
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