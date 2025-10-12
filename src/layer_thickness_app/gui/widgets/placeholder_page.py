from PyQt6.QtWidgets import QWidget, QVBoxLayout
# --- FIX: Use BodyLabel for theme awareness ---
from qfluentwidgets import BodyLabel
from PyQt6.QtCore import Qt

class PlaceholderPage(QWidget):
    """A generic placeholder widget to show which page is active."""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setObjectName(text.replace(" ", "_"))
        
        # --- FIX: Changed QLabel to BodyLabel ---
        self.label = BodyLabel(text)

        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # We can adjust font size if needed, but BodyLabel has good defaults
        self.label.setStyleSheet("font-size: 24px;")

        # Center the label within the page
        self.main_layout = QVBoxLayout(self)
        self.main_layout.addWidget(self.label, 1, Qt.AlignmentFlag.AlignCenter)
