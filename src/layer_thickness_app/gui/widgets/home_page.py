from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from qfluentwidgets import BodyLabel

class HomePage(QWidget):
    """A generic placeholder widget to show which page is active."""
    def __init__(self):
        super().__init__()
        self.text = "Home"
        self.setObjectName(self.text)
        self.label = BodyLabel(self.text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 24px;")
        self.main_layout = QVBoxLayout(self)
        self.main_layout.addWidget(self.label, 1, Qt.AlignmentFlag.AlignCenter)
