import sys

from PyQt6.QtWidgets import QApplication

from layer_thickness_app.controller.main_controller import MainController

def main():
    app = QApplication(sys.argv)
    controller = MainController()
    controller.show_window()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()