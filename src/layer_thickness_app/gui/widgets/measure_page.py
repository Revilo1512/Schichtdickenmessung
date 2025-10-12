import re
from PyQt6.QtWidgets import (
    QWidget, QComboBox, QVBoxLayout, QLabel, QGridLayout, QPushButton,
    QFrame, QLineEdit, QCheckBox, QHBoxLayout, QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont
from PyQt6.QtCore import Qt
from typing import Dict, Any

class MaterialSelector(QFrame):
    """
    A widget with cascading dropdowns to select a material from the catalog.
    It is a QFrame to allow for consistent styling with other panels.
    """
    def __init__(self):
        super().__init__()
        self.data = {}
        self._setup_ui()

    def _setup_ui(self):
        # --- Create Widgets ---
        self.shelf_combo = QComboBox()
        self.book_combo = QComboBox()
        self.page_combo = QComboBox()
        
        # Use models to enable/disable items like dividers
        self.shelf_model = QStandardItemModel()
        self.book_model = QStandardItemModel()
        self.page_model = QStandardItemModel()
        
        self.shelf_combo.setModel(self.shelf_model)
        self.book_combo.setModel(self.book_model)
        self.page_combo.setModel(self.page_model)
        
        self.divider_font = QFont()
        self.divider_font.setItalic(True)

        # Layout
        # Since this is now a QFrame, the layout is set ON the frame itself.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) # Add some internal padding
        layout.addWidget(QLabel("Shelf:"))
        layout.addWidget(self.shelf_combo)
        layout.addWidget(QLabel("Book (Material):"))
        layout.addWidget(self.book_combo)
        layout.addWidget(QLabel("Page (Dataset):"))
        layout.addWidget(self.page_combo)
        layout.addStretch(1) # Pushes dropdowns to the top
        self.setLayout(layout)

        # Connect Signals
        self.shelf_combo.currentIndexChanged.connect(self._on_shelf_changed)
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)

    def populate_data(self, data: Dict[str, Any]):
        """Populates the selector with data from the MaterialService."""
        self.data = data
        self._populate_shelves()

    def _populate_combo(self, combo: QComboBox, items_dict: dict):
        """Helper function to populate a combo box model with items and dividers."""
        model = combo.model()
        model.clear()
        
        for key, data in items_dict.items():
            clean_name = re.sub(r'<[^>]+>', '', data['name'])
            item = QStandardItem()
            item.setData(key, Qt.ItemDataRole.UserRole)
            
            if key.startswith('__DIVIDER'):
                item.setText(f"─ {clean_name} ─")
                item.setFont(self.divider_font)
                item.setEnabled(False) # Make divider unselectable
            else:
                item.setText(clean_name)
                
            model.appendRow(item)

    def _select_first_available(self, combo: QComboBox):
        """Sets the combo box to the first enabled item."""
        model = combo.model()
        for i in range(model.rowCount()):
            if model.item(i).isEnabled():
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(-1)

    def _populate_shelves(self):
        self.shelf_combo.blockSignals(True)
        self._populate_combo(self.shelf_combo, self.data)
        self.shelf_combo.blockSignals(False)
        self._select_first_available(self.shelf_combo)

    def _on_shelf_changed(self, index=-1):
        self.book_combo.blockSignals(True)
        shelf_key = self.shelf_combo.currentData()
        books = self.data.get(shelf_key, {}).get('books', {}) if shelf_key else {}
        self._populate_combo(self.book_combo, books)
        self.book_combo.blockSignals(False)
        self._select_first_available(self.book_combo)

    def _on_book_changed(self, index=-1):
        self.page_combo.blockSignals(True)
        shelf_key = self.shelf_combo.currentData()
        book_key = self.book_combo.currentData()
        pages = {}
        if shelf_key and book_key and not book_key.startswith('__DIVIDER'):
            pages = self.data.get(shelf_key, {}).get('books', {}).get(book_key, {}).get('pages', {})
        self._populate_combo(self.page_combo, pages)
        self.page_combo.blockSignals(False)
        self._select_first_available(self.page_combo)

    def get_selected_path(self) -> str | None:
        """Returns the selected material path or None if incomplete."""
        shelf = self.shelf_combo.currentData()
        book = self.book_combo.currentData()
        page = self.page_combo.currentData()
        if shelf and book and page and not str(book).startswith('__DIVIDER'):
            return f"{shelf}/{book}/{page}"
        return None

class MeasurePage(QWidget):
    """
    Main UI window for the measurement application.
    Arranges all functional components in a 2x2 grid.
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("measurePage")
        self.setWindowTitle("Measurement Tool")
        self._setup_main_layout()

    def _setup_main_layout(self):
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setSpacing(20)

        # --- Create Quadrant Widgets ---
        self.image_capture_tl = self._create_image_capture_widget("Reference Image", "take_reference_image_btn")
        self.image_capture_br = self._create_image_capture_widget("Material Image", "take_material_image_btn")
        self.material_selector = MaterialSelector()
        self.config_panel = self._create_config_widget()

        # --- Style and Add Widgets to Grid ---
        for widget in [self.image_capture_tl, self.image_capture_br, self.material_selector, self.config_panel]:
            widget.setFrameShape(QFrame.Shape.StyledPanel)
            widget.setFrameShadow(QFrame.Shadow.Raised)

        main_layout.addWidget(self.image_capture_tl, 0, 0)
        main_layout.addWidget(self.material_selector, 0, 1)
        main_layout.addWidget(self.image_capture_br, 1, 0)
        main_layout.addWidget(self.config_panel, 1, 1)

        # --- FIX: Set column and row stretch factors ---
        # This tells the grid how to distribute space and fixes both layout issues.
        main_layout.setColumnStretch(0, 1)  # Column 0 (images) gets 2/3 of the width
        main_layout.setColumnStretch(1, 1)  # Column 1 (controls) gets 1/3 of the width
        main_layout.setRowStretch(0, 1)     # Row 0 gets 1/2 of the height
        main_layout.setRowStretch(1, 1)     # Row 1 gets 1/2 of the height

    def _create_image_capture_widget(self, title: str, button_name: str) -> QFrame:
        """Factory method to create a standardized image capture widget."""
        frame = QFrame()
        layout = QVBoxLayout(frame)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        image_placeholder = QLabel("Image Preview")
        image_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_placeholder.setMinimumSize(200, 150)
        image_placeholder.setStyleSheet("background-color: #2E2E2E; color: white; border: 1px solid #555;")
        
        capture_button = QPushButton(f"Take {title}")
        capture_button.setObjectName(button_name)
        
        layout.addWidget(title_label)
        layout.addWidget(image_placeholder, 1) # Give stretch factor to placeholder
        layout.addWidget(capture_button)
        
        return frame

    def _create_config_widget(self) -> QFrame:
        """Factory method to create the configuration and actions panel."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        
        # --- Name Field ---
        name_layout = QHBoxLayout()
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("guest")
        self.name_field.setEnabled(False)
        self.use_name_checkbox = QCheckBox("Name:")
        self.use_name_checkbox.toggled.connect(self.name_field.setEnabled)
        name_layout.addWidget(self.use_name_checkbox)
        name_layout.addWidget(self.name_field)
        
        # --- Save Checkbox ---
        self.save_measurement_checkbox = QCheckBox("Save Measurement?")
        self.save_measurement_checkbox.setChecked(True)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        self.reset_button = QPushButton("Reset")
        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setStyleSheet("font-weight: bold;")
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.calculate_button)

        # --- Assemble Layout ---
        layout.addLayout(name_layout)
        layout.addWidget(self.save_measurement_checkbox)
        layout.addStretch(1) # Pushes buttons to the bottom
        layout.addLayout(button_layout)
        
        return frame

    def populate_material_selector(self, data: Dict[str, Any]):
        """Public method to pass data to the child MaterialSelector widget."""
        self.material_selector.populate_data(data)

