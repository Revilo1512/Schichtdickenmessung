import re
import numpy as np
import logging
from typing import Any

from PyQt6.QtWidgets import (QWidget, QComboBox, QVBoxLayout, QLabel, 
                             QPushButton, QFrame, QLineEdit, QCheckBox, QHBoxLayout)
from PyQt6.QtGui import (QStandardItemModel, QStandardItem, QFont, 
                         QPixmap, QImage)
from PyQt6.QtCore import Qt, pyqtSignal
from qfluentwidgets import InfoBar, InfoBarPosition

logger = logging.getLogger(__name__)

class MaterialSelector(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("material_selector_frame")
        self.data: dict[str, Any] = {}
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._setup_ui()

    def _setup_ui(self):
        self.shelf_combo = QComboBox()
        self.book_combo = QComboBox()
        self.page_combo = QComboBox()
        
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
        self.header_font.setPointSize(10)

        shelf_label = QLabel("Shelf (Category):")
        book_label = QLabel("Book (Material):")
        page_label = QLabel("Page (Dataset):")

        shelf_label.setFont(self.header_font)
        book_label.setFont(self.header_font)
        page_label.setFont(self.header_font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(shelf_label)
        layout.addWidget(self.shelf_combo)
        layout.addWidget(book_label)
        layout.addWidget(self.book_combo)
        layout.addWidget(page_label)
        layout.addWidget(self.page_combo)
        self.setLayout(layout)

        self.shelf_combo.currentIndexChanged.connect(self._on_shelf_changed)
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)

    def populate_data(self, data: dict[str, Any]):
        self.data = data
        self._populate_shelves()

    def _populate_combo(self, combo: QComboBox, items_dict: dict):
        model = combo.model()
        model.clear()
        
        for key, data in items_dict.items():
            clean_name = re.sub(r'<[^>]+>', '', data['name'])
            item = QStandardItem()
            item.setData(key, Qt.ItemDataRole.UserRole)
            
            if key.startswith('__DIVIDER'):
                item.setText(f"─ {clean_name} ─")
                item.setFont(self.divider_font)
                item.setEnabled(False)
            else:
                item.setText(clean_name)
                
            model.appendRow(item)

    def _select_first_available(self, combo: QComboBox):
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
        shelf = self.shelf_combo.currentData()
        book = self.book_combo.currentData()
        page = self.page_combo.currentData()
        if shelf and book and page and not str(book).startswith('__DIVIDER'):
            return f"{shelf}/{book}/{page}"
        return None

class MeasurePage(QWidget):
    # --- NEU: Eigene, abstrakte Signale für die saubere Kommunikation ---
    config_changed = pyqtSignal()
    calculation_requested = pyqtSignal()
    capture_reference_requested = pyqtSignal()
    capture_material_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setObjectName("measurePage")
        self.setWindowTitle("Measurement Tool")

        self.reference_image: np.ndarray | None = None
        self.material_image: np.ndarray | None = None

        self._setup_main_layout()
        self._connect_internal_signals()

    def _setup_main_layout(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setSpacing(20)

        self.image_capture_tl = self._create_image_capture_widget("Reference Image", "reference_image")
        self.image_capture_br = self._create_image_capture_widget("Material Image", "material_image")
        self.config_and_selector_panel = self._create_config_and_selector_widget()
        self.result_panel = self._create_result_widget()

        for widget in [self.image_capture_tl, self.image_capture_br, 
                       self.config_and_selector_panel, self.result_panel]:
            widget.setFrameShape(QFrame.Shape.StyledPanel)
            widget.setFrameShadow(QFrame.Shadow.Raised)
            
        left_column_container = QWidget() 
        left_layout = QVBoxLayout(left_column_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)
        left_layout.addWidget(self.image_capture_tl, 1)
        left_layout.addWidget(self.image_capture_br, 1)

        right_column_container = QWidget() 
        right_layout = QVBoxLayout(right_column_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(20)
        right_layout.addWidget(self.config_and_selector_panel, 1)
        right_layout.addWidget(self.result_panel, 1)

        main_layout.addWidget(left_column_container, 1)
        main_layout.addWidget(right_column_container, 1)
        
        self.ref_image_button = self.image_capture_tl.findChild(QPushButton, "reference_image_btn")
        self.mat_image_button = self.image_capture_br.findChild(QPushButton, "material_image_btn")
        self.ref_image_label = self.image_capture_tl.findChild(QLabel, "reference_image_preview")
        self.mat_image_label = self.image_capture_br.findChild(QLabel, "material_image_preview")
        
        self.material_selector = self.config_and_selector_panel.findChild(MaterialSelector)
        self.wavelength_combo = self.config_and_selector_panel.findChild(QComboBox, "wavelength_combo")
        self.calculate_button = self.config_and_selector_panel.findChild(QPushButton, "calculate_button")
        self.reset_button = self.config_and_selector_panel.findChild(QPushButton, "reset_button")
        self.use_name_checkbox = self.config_and_selector_panel.findChild(QCheckBox, "use_name_checkbox")
        self.name_field = self.config_and_selector_panel.findChild(QLineEdit, "name_field")
        self.save_measurement_checkbox = self.config_and_selector_panel.findChild(QCheckBox, "save_measurement_checkbox")
        self.note_field = self.config_and_selector_panel.findChild(QLineEdit, "note_field")
        self.result_label = self.result_panel.findChild(QLabel, "result_label")

    def _connect_internal_signals(self):
        """Verbindet interne UI-Events mit unseren sauberen, öffentlichen Signalen."""
        self.calculate_button.clicked.connect(self.calculation_requested.emit)
        self.ref_image_button.clicked.connect(self.capture_reference_requested.emit)
        self.mat_image_button.clicked.connect(self.capture_material_requested.emit)
        self.reset_button.clicked.connect(self.reset_requested.emit)

        # Signale für Konfigurationsänderungen
        self.material_selector.page_combo.currentIndexChanged.connect(self.config_changed.emit)
        self.wavelength_combo.currentIndexChanged.connect(self.config_changed.emit)
        self.name_field.textChanged.connect(self.config_changed.emit)
        self.use_name_checkbox.toggled.connect(self.config_changed.emit)
        self.save_measurement_checkbox.toggled.connect(self.config_changed.emit)
        self.note_field.textChanged.connect(self.config_changed.emit)

    def _create_image_capture_widget(self, title: str, button_name: str) -> QFrame:
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
        layout.addWidget(image_placeholder, 1)
        layout.addWidget(capture_button)
        return frame

    def _create_config_and_selector_widget(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(10)

        self.material_selector = MaterialSelector()
        layout.addWidget(self.material_selector)

        layout.addSpacing(15)
        wavelength_label = QLabel("Wavelength:")
        wavelength_label.setFont(header_font)
        self.wavelength_combo = QComboBox()
        self.wavelength_combo.setObjectName("wavelength_combo")
        self.wavelength_combo.addItem("Red (635 nm)", 0.635)
        self.wavelength_combo.addItem("Green (532 nm)", 0.532)
        layout.addWidget(wavelength_label)
        layout.addWidget(self.wavelength_combo)

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
        
        layout.addSpacing(10)
        self.save_measurement_checkbox = QCheckBox("Save Measurement?")
        self.save_measurement_checkbox.setObjectName("save_measurement_checkbox")
        self.save_measurement_checkbox.setChecked(True)
        self.save_measurement_checkbox.setFont(header_font)
        layout.addWidget(self.save_measurement_checkbox)

        layout.addSpacing(10)
        note_label = QLabel("Note:")
        note_label.setFont(header_font)
        self.note_field = QLineEdit()
        self.note_field.setObjectName("note_field")
        self.note_field.setPlaceholderText("Optional note...")
        layout.addWidget(note_label)
        layout.addWidget(self.note_field)

        layout.addStretch(1)

        button_layout = QHBoxLayout()
        large_button_style = "font-size: 12pt;"

        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet(large_button_style)
        self.reset_button.setObjectName("reset_button")

        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setStyleSheet(f"{large_button_style} font-weight: bold;")
        self.calculate_button.setObjectName("calculate_button")
        self.calculate_button.setEnabled(False) # Initial deaktiviert
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.calculate_button)
        layout.addLayout(button_layout)
        
        return frame

    def _create_result_widget(self) -> QFrame:
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
        
    def get_measurement_data(self) -> dict[str, Any]:
        """NEU: Bündelt alle UI-Eingaben für den Controller."""
        return {
            "ref_image": self.reference_image,
            "mat_image": self.material_image,
            "material_path": self.material_selector.get_selected_path(),
            "wavelength_um": self.wavelength_combo.currentData(),
            "save_checked": self.save_measurement_checkbox.isChecked(),
            "use_name": self.use_name_checkbox.isChecked(),
            "name": self.name_field.text(),
            "note": self.note_field.text()
        }

    def reset_all(self):
        self.reference_image = None
        self.material_image = None
        
        for label in [self.ref_image_label, self.mat_image_label]:
            label.setText("Image Preview")
            label.setStyleSheet("background-color: #2E2E2E; color: white; border: 1px solid #555;")
            
        self.wavelength_combo.blockSignals(True)
        self.use_name_checkbox.blockSignals(True)
        self.name_field.blockSignals(True)
        self.save_measurement_checkbox.blockSignals(True)
        self.note_field.blockSignals(True)

        self.wavelength_combo.setCurrentIndex(0)
        self.use_name_checkbox.setChecked(False)
        self.name_field.setText("")
        self.save_measurement_checkbox.setChecked(True)
        self.note_field.setText("")
        self.calculate_button.setEnabled(False)
        
        self.wavelength_combo.blockSignals(False)
        self.use_name_checkbox.blockSignals(False)
        self.name_field.blockSignals(False)
        self.save_measurement_checkbox.blockSignals(False)
        self.note_field.blockSignals(False)
            
        if hasattr(self, 'material_selector'):
            self.material_selector.page_combo.blockSignals(True)
            self.material_selector._populate_shelves()
            self.material_selector.page_combo.blockSignals(False)
            
        self.set_result_text("Result...")

    def populate_material_selector(self, data: dict[str, Any]):
        if hasattr(self, 'material_selector'):
            self.material_selector.populate_data(data)

    def set_result_text(self, text: str, append: bool = False):
        if hasattr(self, 'result_label'):
            if append:
                current_text = self.result_label.text()
                if "Saved!" not in current_text:
                    self.result_label.setText(f"{current_text}<br>Saved!")
            else:
                self.result_label.setText(text)

    def set_calculation_enabled(self, enabled: bool):
        """Erlaubt dem Controller, den Button zu steuern."""
        self.calculate_button.setEnabled(enabled)

    def _convert_np_to_pixmap(self, image_array: np.ndarray | None) -> QPixmap:
        if image_array is None:
            return QPixmap()
        try:
            if image_array.ndim != 3:
                logger.error("Error converting image: Expected 3 dimensions, got %s", image_array.ndim)
                return QPixmap()
            height, width, channels = image_array.shape
            if channels != 3:
                logger.error("Error converting image: Expected 3 channels, got %s", channels)
                return QPixmap()

            stride = image_array.strides[0]
            q_image = QImage(image_array.data, width, height, stride, QImage.Format.Format_BGR888).copy()
            return QPixmap.fromImage(q_image)
        except Exception as e:
            logger.error("Error converting image: %s", e)
            return QPixmap()

    def set_image(self, image_data: np.ndarray | None, image_type: str):
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
            scaled_pixmap = pixmap.scaled(
                target_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            target_label.setPixmap(scaled_pixmap)

    def show_info_bar(self, title: str, content: str, is_error: bool = False):
        if is_error:
            InfoBar.error(title=title, content=content, duration=5000, parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.success(title=title, content=content, duration=3000, parent=self, position=InfoBarPosition.TOP)