import re
import numpy as np
from typing import Dict, Any

from PyQt6.QtWidgets import (QWidget, QComboBox, QVBoxLayout, QLabel, QGridLayout, 
                             QPushButton, QFrame, QLineEdit, QCheckBox, QHBoxLayout)
from PyQt6.QtGui import (QStandardItemModel, QStandardItem, QFont, 
                         QPixmap, QImage, QPalette, QColor)
from PyQt6.QtCore import Qt

class MaterialSelector(QFrame):
    """
    A widget with cascading dropdowns to select a material from the refractive index database catalog.
    This is now a sub-widget, intended to be placed inside other panels.
    """
    def __init__(self):
        super().__init__()
        self.data = {}
        # Remove frame styling, as it will be part of a larger frame
        self.setFrameShape(QFrame.Shape.NoFrame)
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
        self.divider_font.setBold(True)

        self.header_font = QFont()
        self.header_font.setBold(True)
        self.header_font.setPointSize(10) # Slightly larger font for headers

        # Create the labels and apply the bold font
        shelf_label = QLabel("Shelf (Category):")
        book_label = QLabel("Book (Material):")
        page_label = QLabel("Page (Dataset):")

        shelf_label.setFont(self.header_font)
        book_label.setFont(self.header_font)
        page_label.setFont(self.header_font)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0) # No margins, container will handle it
        layout.addWidget(shelf_label)
        layout.addWidget(self.shelf_combo)
        layout.addWidget(book_label)
        layout.addWidget(self.book_combo)
        layout.addWidget(page_label)
        layout.addWidget(self.page_combo)
        # We no longer add stretch, allowing the parent layout to manage it
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

        self.reference_image: np.ndarray | None = None
        self.material_image: np.ndarray | None = None

        self._setup_main_layout()

    def _setup_main_layout(self):
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setSpacing(20)

        # Set the background color for the entire page (the "gutters")
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#CDDEEC"))
        self.setPalette(palette)

        self.image_capture_tl = self._create_image_capture_widget("Reference Image", "reference_image")
        self.image_capture_br = self._create_image_capture_widget("Material Image", "material_image")
        
        self.config_and_selector_panel = self._create_config_and_selector_widget()
        self.result_panel = self._create_result_widget()

        # --- Style and Add Widgets to Grid ---
        for widget in [self.image_capture_tl, self.image_capture_br, 
                       self.config_and_selector_panel, self.result_panel]:
            widget.setFrameShape(QFrame.Shape.StyledPanel)
            widget.setFrameShadow(QFrame.Shadow.Raised)
            widget.setAutoFillBackground(True)
            p = widget.palette()
            p.setColor(QPalette.ColorRole.Window, QColor("white"))
            widget.setPalette(p)


        # Add the 4 widgets to the grid
        main_layout.addWidget(self.image_capture_tl, 0, 0)
        main_layout.addWidget(self.config_and_selector_panel, 0, 1) # Top-right
        main_layout.addWidget(self.image_capture_br, 1, 0)
        main_layout.addWidget(self.result_panel, 1, 1)               # Bottom-right

        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 1)
        main_layout.setRowStretch(0, 1)
        main_layout.setRowStretch(1, 1)

        # --- Find Widgets for Controller ---
        
        # Find image buttons and labels
        self.ref_image_button = self.image_capture_tl.findChild(QPushButton, "reference_image_btn")
        self.mat_image_button = self.image_capture_br.findChild(QPushButton, "material_image_btn")
        self.ref_image_label = self.image_capture_tl.findChild(QLabel, "reference_image_preview")
        self.mat_image_label = self.image_capture_br.findChild(QLabel, "material_image_preview")
        
        # Find widgets from the combined panel
        self.material_selector = self.config_and_selector_panel.findChild(MaterialSelector)
        self.wavelength_combo = self.config_and_selector_panel.findChild(QComboBox, "wavelength_combo")
        self.calculate_button = self.config_and_selector_panel.findChild(QPushButton, "calculate_button")
        self.reset_button = self.config_and_selector_panel.findChild(QPushButton, "reset_button")
        self.use_name_checkbox = self.config_and_selector_panel.findChild(QCheckBox, "use_name_checkbox")
        self.name_field = self.config_and_selector_panel.findChild(QLineEdit, "name_field")
        self.save_measurement_checkbox = self.config_and_selector_panel.findChild(QCheckBox, "save_measurement_checkbox")

        # Find the result label
        self.result_label = self.result_panel.findChild(QLabel, "result_label")


    def _create_image_capture_widget(self, title: str, button_name: str) -> QFrame:
        """Factory method to create a standardized image capture widget."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(12)

        title_label = QLabel(title)
        title_label.setFont(header_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        image_placeholder = QLabel("Image Preview")
        image_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_placeholder.setMinimumSize(200, 150)
        image_placeholder.setStyleSheet("background-color: #2E2E2E; color: white; border: 1px solid #555;")
        image_placeholder.setObjectName(f"{button_name}_preview")
        
        capture_button = QPushButton(f"Take {title}")
        capture_button.setObjectName(f"{button_name}_btn")
        
        layout.addWidget(title_label)
        layout.addWidget(image_placeholder, 1) # Give stretch factor to placeholder
        layout.addWidget(capture_button)
        
        return frame

    def _create_config_and_selector_widget(self) -> QFrame:
        """
        NEW: Creates a single widget holding both the MaterialSelector
        and the configuration options (wavelength, user, buttons).
        """
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(10)

        # --- 1. Material Selector ---
        self.material_selector = MaterialSelector()
        layout.addWidget(self.material_selector)

        # --- 2. Wavelength Selector ---
        layout.addSpacing(15)
        wavelength_label = QLabel("Wavelength:")
        wavelength_label.setFont(header_font)
        self.wavelength_combo = QComboBox()
        self.wavelength_combo.setObjectName("wavelength_combo")
        # Add items with text and associated data (in micrometers)
        self.wavelength_combo.addItem("Red (635 nm)", 0.635)
        self.wavelength_combo.addItem("Green (532 nm)", 0.532)
        layout.addWidget(wavelength_label)
        layout.addWidget(self.wavelength_combo)

        # --- 3. Name Field ---
        layout.addSpacing(15)
        self.name_field = QLineEdit()
        self.name_field.setObjectName("name_field")
        self.name_field.setPlaceholderText("Guest")
        self.name_field.setEnabled(False)
        self.use_name_checkbox = QCheckBox("Name:")
        self.use_name_checkbox.setObjectName("use_name_checkbox")
        self.use_name_checkbox.setFont(header_font)
        self.use_name_checkbox.toggled.connect(self.name_field.setEnabled)
        
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.use_name_checkbox)
        name_layout.addWidget(self.name_field)
        layout.addLayout(name_layout)
        
        # --- 4. Save Checkbox ---
        layout.addSpacing(10)
        self.save_measurement_checkbox = QCheckBox("Save Measurement?")
        self.save_measurement_checkbox.setObjectName("save_measurement_checkbox")
        self.save_measurement_checkbox.setChecked(True)
        self.save_measurement_checkbox.setFont(header_font)
        layout.addWidget(self.save_measurement_checkbox)

        # --- 5. Spacer ---
        layout.addStretch(1) # Pushes buttons to the bottom

        # --- 6. Action Buttons ---
        button_layout = QHBoxLayout()
        large_button_style = "font-size: 12pt;"

        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet(large_button_style)
        self.reset_button.setObjectName("reset_button")

        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setStyleSheet(f"{large_button_style} font-weight: bold;")
        self.calculate_button.setObjectName("calculate_button")
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.calculate_button)
        layout.addLayout(button_layout)
        
        return frame

    def _create_result_widget(self) -> QFrame:
        """
        Creates the bottom-right widget to display calculation results.
        """
        frame = QFrame()
        layout = QVBoxLayout(frame)
        
        self.result_label = QLabel("Result...")
        self.result_label.setObjectName("result_label")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        result_font = QFont()
        result_font.setBold(True)
        result_font.setPointSize(18)
        self.result_label.setFont(result_font)
        
        layout.addWidget(self.result_label)
        return frame

    def populate_material_selector(self, data: Dict[str, Any]):
        """Public method to pass data to the child MaterialSelector widget."""
        if hasattr(self, 'material_selector'):
            self.material_selector.populate_data(data)

    def set_result_text(self, text: str, append: bool = False):
        """
        Public method for the controller to update the result label.
        If append is True, it adds to the existing text.
        """
        if hasattr(self, 'result_label'):
            if append:
                current_text = self.result_label.text()
                # Avoid appending "Saved!" multiple times
                if "Saved!" not in current_text:
                    self.result_label.setText(f"{current_text}<br>Saved!")
            else:
                self.result_label.setText(text)

    def _convert_np_to_pixmap(self, image_array: np.ndarray) -> QPixmap:
        """Converts a BGR NumPy array to a QPixmap."""
        if image_array is None:
            return QPixmap()

        try:
            if image_array.ndim != 3:
                print(f"Error converting image: Expected 3 dimensions, got {image_array.ndim}")
                return QPixmap()
            height, width, channels = image_array.shape
            if channels != 3:
                print(f"Error converting image: Expected 3 channels, got {channels}")
                return QPixmap()

            stride = image_array.strides[0]
            q_image = QImage(image_array.data, 
                             width, 
                             height, 
                             stride, 
                             QImage.Format.Format_BGR888).copy()
            return QPixmap.fromImage(q_image)
        except Exception as e:
            print(f"Error converting image: {e}")
            return QPixmap()

    def set_image(self, image_data: np.ndarray, image_type: str):
        """
        Public method to set a captured image.
        Stores the NumPy array and displays the converted QPixmap.
        """
        if image_data is None:
            return

        pixmap = self._convert_np_to_pixmap(image_data)
        
        target_label = None
        if image_type == "reference":
            self.reference_image = image_data
            target_label = self.ref_image_label
        elif image_type == "material":
            self.material_image = image_data
            target_label = self.mat_image_label

        if target_label:
            # Scale the pixmap to fit the label while keeping aspect ratio
            scaled_pixmap = pixmap.scaled(
                target_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            target_label.setPixmap(scaled_pixmap)
