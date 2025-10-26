import sys, os

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer

from layer_thickness_app.controller.main_controller import MainController
from layer_thickness_app.config.config import cfg
from qfluentwidgets import setTheme

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


def main():
    app = QApplication(sys.argv)
    
    splash = SplashWindow("src/layer_thickness_app/gui/resources/duck_icon.svg")
    splash.show()

    # force render immediately
    app.processEvents()

    controller = MainController()

    cfg.load("src\layer_thickness_app\config\config.json", cfg)
    setTheme(cfg.themeMode.value)

    # close splash manually and show main window
    def show_main():
        screen = app.primaryScreen().availableGeometry()
        x = (screen.width() - 1100) // 2
        y = (screen.height() - 800) // 2
        controller.view.setGeometry(x, y, 1100, 800)
        controller.show_window()
        splash.close()
    
    QTimer.singleShot(800, show_main)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
