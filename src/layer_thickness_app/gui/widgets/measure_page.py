from __future__ import annotations

import re
import numpy as np
import logging
from typing import Any, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QComboBox, QVBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QCheckBox, QHBoxLayout,
    QSpinBox, QDoubleSpinBox, QGridLayout,
)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont, QPixmap, QImage
from PyQt6.QtCore import Qt, pyqtSignal
from qfluentwidgets import InfoBar, InfoBarPosition

if TYPE_CHECKING:
    from layer_thickness_app.services.camera_service import FrameCaptureResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MaterialSelector (unchanged from Step 4)
# ---------------------------------------------------------------------------
class MaterialSelector(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("material_selector_frame")
        self.data: dict[str, Any] = {}
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._setup_ui()

    def _setup_ui(self):
        self.shelf_combo = QComboBox()
        self.book_combo  = QComboBox()
        self.page_combo  = QComboBox()

        self.shelf_model = QStandardItemModel()
        self.book_model  = QStandardItemModel()
        self.page_model  = QStandardItemModel()

        self.shelf_combo.setModel(self.shelf_model)
        self.book_combo.setModel(self.book_model)
        self.page_combo.setModel(self.page_model)

        self.divider_font = QFont()
        self.divider_font.setItalic(True); self.divider_font.setBold(True)

        self.header_font = QFont()
        self.header_font.setBold(True); self.header_font.setPointSize(10)

        shelf_label = QLabel("Shelf (Category):"); shelf_label.setFont(self.header_font)
        book_label  = QLabel("Book (Material):");  book_label.setFont(self.header_font)
        page_label  = QLabel("Page (Dataset):");   page_label.setFont(self.header_font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(shelf_label); layout.addWidget(self.shelf_combo)
        layout.addWidget(book_label);  layout.addWidget(self.book_combo)
        layout.addWidget(page_label);  layout.addWidget(self.page_combo)
        self.setLayout(layout)

        self.shelf_combo.currentIndexChanged.connect(self._on_shelf_changed)
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)

    def populate_data(self, data: dict[str, Any]):
        self.data = data
        self._populate_shelves()

    def _populate_combo(self, combo: QComboBox, items_dict: dict):
        model = combo.model(); model.clear()
        for key, data in items_dict.items():
            clean_name = re.sub(r"<[^>]+>", "", data["name"])
            item = QStandardItem()
            item.setData(key, Qt.ItemDataRole.UserRole)
            if key.startswith("__DIVIDER"):
                item.setText(f"─ {clean_name} ─")
                item.setFont(self.divider_font); item.setEnabled(False)
            else:
                item.setText(clean_name)
            model.appendRow(item)

    def _select_first_available(self, combo: QComboBox):
        model = combo.model()
        for i in range(model.rowCount()):
            if model.item(i).isEnabled():
                combo.setCurrentIndex(i); return
        combo.setCurrentIndex(-1)

    def _populate_shelves(self):
        self.shelf_combo.blockSignals(True)
        self._populate_combo(self.shelf_combo, self.data)
        self.shelf_combo.blockSignals(False)
        self._select_first_available(self.shelf_combo)

    def _on_shelf_changed(self, index=-1):
        self.book_combo.blockSignals(True)
        shelf_key = self.shelf_combo.currentData()
        books = self.data.get(shelf_key, {}).get("books", {}) if shelf_key else {}
        self._populate_combo(self.book_combo, books)
        self.book_combo.blockSignals(False)
        self._select_first_available(self.book_combo)

    def _on_book_changed(self, index=-1):
        self.page_combo.blockSignals(True)
        shelf_key = self.shelf_combo.currentData()
        book_key  = self.book_combo.currentData()
        pages = {}
        if shelf_key and book_key and not book_key.startswith("__DIVIDER"):
            pages = (self.data.get(shelf_key, {})
                              .get("books", {}).get(book_key, {})
                              .get("pages", {}))
        self._populate_combo(self.page_combo, pages)
        self.page_combo.blockSignals(False)
        self._select_first_available(self.page_combo)

    def get_selected_path(self) -> str | None:
        shelf = self.shelf_combo.currentData()
        book  = self.book_combo.currentData()
        page  = self.page_combo.currentData()
        if shelf and book and page and not str(book).startswith("__DIVIDER"):
            return f"{shelf}/{book}/{page}"
        return None


# ---------------------------------------------------------------------------
# MeasurePage
# ---------------------------------------------------------------------------
class MeasurePage(QWidget):
    """
    Step 8 additions
    ----------------
    • Collapsible "Calibration Mode" section with:
        - Reference Thickness input (QDoubleSpinBox, 0.0 – 5000 nm,
          0.0 = disabled / no reference)
        - Session Tag input (QLineEdit, free text)
    • Both fields are optional and default to "off", so normal
      measurement workflows are unchanged.
    • get_measurement_data() returns the two new fields, which the
      controller merges into the DB save dict when non-empty.
    """

    config_changed              = pyqtSignal()
    calculation_requested       = pyqtSignal()
    capture_reference_requested = pyqtSignal()
    capture_material_requested  = pyqtSignal()
    reset_requested             = pyqtSignal()

    FRAME_COUNT_MIN     = 1
    FRAME_COUNT_MAX     = 100
    FRAME_COUNT_DEFAULT = 30

    # Reference-thickness input bounds (nm).  0 = "not set".
    REF_NM_MIN:     float = 0.0
    REF_NM_MAX:     float = 5000.0
    REF_NM_DEFAULT: float = 0.0

    def __init__(self):
        super().__init__()
        self.setObjectName("measurePage")
        self.setWindowTitle("Measurement Tool")

        self.reference_capture: "FrameCaptureResult | None" = None
        self.material_capture:  "FrameCaptureResult | None" = None

        self._setup_main_layout()
        self._connect_internal_signals()

    # ==================================================================
    # Layout
    # ==================================================================

    def _setup_main_layout(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setSpacing(20)

        self.image_capture_tl          = self._create_image_capture_widget("Reference Image", "reference_image")
        self.image_capture_br          = self._create_image_capture_widget("Material Image",  "material_image")
        self.config_and_selector_panel = self._create_config_and_selector_widget()
        self.result_panel              = self._create_result_widget()

        for widget in (
            self.image_capture_tl, self.image_capture_br,
            self.config_and_selector_panel, self.result_panel,
        ):
            widget.setFrameShape(QFrame.Shape.StyledPanel)
            widget.setFrameShadow(QFrame.Shadow.Raised)

        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0); left_layout.setSpacing(20)
        left_layout.addWidget(self.image_capture_tl, 1)
        left_layout.addWidget(self.image_capture_br, 1)

        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0); right_layout.setSpacing(20)
        right_layout.addWidget(self.config_and_selector_panel, 1)
        right_layout.addWidget(self.result_panel, 1)

        main_layout.addWidget(left_column,  1)
        main_layout.addWidget(right_column, 1)

        # Grab references to child widgets that we need to interact with
        self.ref_image_button = self.image_capture_tl.findChild(QPushButton, "reference_image_btn")
        self.mat_image_button = self.image_capture_br.findChild(QPushButton, "material_image_btn")
        self.ref_image_label  = self.image_capture_tl.findChild(QLabel,      "reference_image_preview")
        self.mat_image_label  = self.image_capture_br.findChild(QLabel,      "material_image_preview")
        self.ref_stats_label  = self.image_capture_tl.findChild(QLabel,      "reference_image_stats")
        self.mat_stats_label  = self.image_capture_br.findChild(QLabel,      "material_image_stats")

        self.material_selector         = self.config_and_selector_panel.findChild(MaterialSelector)
        self.wavelength_combo          = self.config_and_selector_panel.findChild(QComboBox, "wavelength_combo")
        self.frame_count_spinbox       = self.config_and_selector_panel.findChild(QSpinBox,  "frame_count_spinbox")
        self.calibration_mode_checkbox = self.config_and_selector_panel.findChild(QCheckBox, "calibration_mode_checkbox")
        self.reference_thickness_spin  = self.config_and_selector_panel.findChild(QDoubleSpinBox, "reference_thickness_spin")
        self.session_tag_field         = self.config_and_selector_panel.findChild(QLineEdit, "session_tag_field")
        self.calculate_button          = self.config_and_selector_panel.findChild(QPushButton, "calculate_button")
        self.reset_button              = self.config_and_selector_panel.findChild(QPushButton, "reset_button")
        self.use_name_checkbox         = self.config_and_selector_panel.findChild(QCheckBox, "use_name_checkbox")
        self.name_field                = self.config_and_selector_panel.findChild(QLineEdit, "name_field")
        self.save_measurement_checkbox = self.config_and_selector_panel.findChild(QCheckBox, "save_measurement_checkbox")
        self.note_field                = self.config_and_selector_panel.findChild(QLineEdit, "note_field")
        self.result_label              = self.result_panel.findChild(QLabel, "result_label")

    def _connect_internal_signals(self):
        self.calculate_button.clicked.connect(self.calculation_requested.emit)
        self.ref_image_button.clicked.connect(self.capture_reference_requested.emit)
        self.mat_image_button.clicked.connect(self.capture_material_requested.emit)
        self.reset_button.clicked.connect(self.reset_requested.emit)

        # Config-change signals
        self.material_selector.page_combo.currentIndexChanged.connect(self.config_changed.emit)
        self.wavelength_combo.currentIndexChanged.connect(self.config_changed.emit)
        self.frame_count_spinbox.valueChanged.connect(self.config_changed.emit)
        self.reference_thickness_spin.valueChanged.connect(self.config_changed.emit)
        self.session_tag_field.textChanged.connect(self.config_changed.emit)
        self.name_field.textChanged.connect(self.config_changed.emit)
        self.use_name_checkbox.toggled.connect(self.config_changed.emit)
        self.save_measurement_checkbox.toggled.connect(self.config_changed.emit)
        self.note_field.textChanged.connect(self.config_changed.emit)

        # Calibration-mode toggle
        self.calibration_mode_checkbox.toggled.connect(self._on_calibration_mode_toggled)

    # ==================================================================
    # Widget builders
    # ==================================================================

    def _create_image_capture_widget(self, title: str, button_name: str) -> QFrame:
        frame  = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        header_font = QFont(); header_font.setBold(True); header_font.setPointSize(12)
        stats_font  = QFont(); stats_font.setPointSize(8)

        title_label = QLabel(title); title_label.setFont(header_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        image_placeholder = QLabel("Image Preview")
        image_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_placeholder.setMinimumSize(200, 150)
        image_placeholder.setStyleSheet(
            "background-color: #2E2E2E; color: white; border: 1px solid #555;"
        )
        image_placeholder.setObjectName(f"{button_name}_preview")

        stats_label = QLabel("")
        stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_label.setFont(stats_font)
        stats_label.setStyleSheet("color: gray;")
        stats_label.setObjectName(f"{button_name}_stats")
        stats_label.setMinimumHeight(14)

        capture_button = QPushButton(f"Take {title}")
        capture_button.setObjectName(f"{button_name}_btn")

        layout.addWidget(title_label)
        layout.addWidget(image_placeholder, 1)
        layout.addWidget(stats_label)
        layout.addWidget(capture_button)
        return frame

    def _create_config_and_selector_widget(self) -> QFrame:
        frame  = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        header_font = QFont(); header_font.setBold(True); header_font.setPointSize(10)
        hint_font   = QFont(); hint_font.setPointSize(8)

        # --- Material selector ----------------------------------------
        self.material_selector = MaterialSelector()
        layout.addWidget(self.material_selector)

        # --- Wavelength ----------------------------------------------
        layout.addSpacing(15)
        wavelength_label = QLabel("Wavelength:"); wavelength_label.setFont(header_font)
        self.wavelength_combo = QComboBox()
        self.wavelength_combo.setObjectName("wavelength_combo")
        self.wavelength_combo.addItem("Red (635 nm)",   0.635)
        self.wavelength_combo.addItem("Green (532 nm)", 0.532)
        layout.addWidget(wavelength_label)
        layout.addWidget(self.wavelength_combo)

        # --- Frame count ----------------------------------------------
        layout.addSpacing(15)
        frame_count_label = QLabel("Frames per Capture:")
        frame_count_label.setFont(header_font)
        self.frame_count_spinbox = QSpinBox()
        self.frame_count_spinbox.setObjectName("frame_count_spinbox")
        self.frame_count_spinbox.setRange(self.FRAME_COUNT_MIN, self.FRAME_COUNT_MAX)
        self.frame_count_spinbox.setValue(self.FRAME_COUNT_DEFAULT)
        self.frame_count_spinbox.setToolTip(
            "Number of frames to average per capture.\n"
            "1 = single-frame mode (Burkhardt baseline). Recommended for calibration: 30."
        )
        frame_hint = QLabel("Higher = less noise, slower capture")
        frame_hint.setFont(hint_font); frame_hint.setStyleSheet("color: gray;")
        layout.addWidget(frame_count_label)
        layout.addWidget(self.frame_count_spinbox)
        layout.addWidget(frame_hint)

        # --- Calibration-mode section (NEW in Step 8) -----------------
        layout.addSpacing(15)
        self.calibration_mode_checkbox = QCheckBox("Calibration Mode")
        self.calibration_mode_checkbox.setObjectName("calibration_mode_checkbox")
        self.calibration_mode_checkbox.setFont(header_font)
        self.calibration_mode_checkbox.setToolTip(
            "Enable to tag measurements with a known Reference Thickness\n"
            "and a Session Tag — these are required by the Calibration and\n"
            "Validation pages to fit regression models and run MSA studies."
        )
        layout.addWidget(self.calibration_mode_checkbox)

        self.calibration_mode_frame = QFrame()
        self.calibration_mode_frame.setObjectName("calibration_mode_frame")
        cal_grid = QGridLayout(self.calibration_mode_frame)
        cal_grid.setContentsMargins(0, 5, 0, 0)
        cal_grid.setSpacing(8)

        ref_label = QLabel("Reference:"); ref_label.setFont(header_font)
        self.reference_thickness_spin = QDoubleSpinBox()
        self.reference_thickness_spin.setObjectName("reference_thickness_spin")
        self.reference_thickness_spin.setRange(self.REF_NM_MIN, self.REF_NM_MAX)
        self.reference_thickness_spin.setDecimals(2)
        self.reference_thickness_spin.setSingleStep(1.0)
        self.reference_thickness_spin.setValue(self.REF_NM_DEFAULT)
        self.reference_thickness_spin.setSuffix(" nm")
        self.reference_thickness_spin.setSpecialValueText("— not set —")
        self.reference_thickness_spin.setToolTip(
            "Known true thickness of the sample, in nanometres.\n"
            "Set to 0 to leave blank (measurement won't be usable for calibration)."
        )

        session_label = QLabel("Session tag:"); session_label.setFont(header_font)
        self.session_tag_field = QLineEdit()
        self.session_tag_field.setObjectName("session_tag_field")
        self.session_tag_field.setPlaceholderText("e.g. Cu_cal_2026-04")
        self.session_tag_field.setToolTip(
            "Free-form label used to group measurements into one test run.\n"
            "The calibration and validation pages filter by this tag."
        )

        cal_grid.addWidget(ref_label,                   0, 0)
        cal_grid.addWidget(self.reference_thickness_spin, 0, 1)
        cal_grid.addWidget(session_label,                 1, 0)
        cal_grid.addWidget(self.session_tag_field,        1, 1)
        cal_grid.setColumnStretch(1, 1)

        layout.addWidget(self.calibration_mode_frame)
        # Collapsed by default
        self.calibration_mode_frame.setVisible(False)

        # --- Name field ----------------------------------------------
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

        # --- Save checkbox -------------------------------------------
        layout.addSpacing(10)
        self.save_measurement_checkbox = QCheckBox("Save Measurement?")
        self.save_measurement_checkbox.setObjectName("save_measurement_checkbox")
        self.save_measurement_checkbox.setChecked(True)
        self.save_measurement_checkbox.setFont(header_font)
        layout.addWidget(self.save_measurement_checkbox)

        # --- Note ----------------------------------------------------
        layout.addSpacing(10)
        note_label = QLabel("Note:"); note_label.setFont(header_font)
        self.note_field = QLineEdit()
        self.note_field.setObjectName("note_field")
        self.note_field.setPlaceholderText("Optional note...")
        layout.addWidget(note_label)
        layout.addWidget(self.note_field)

        layout.addStretch(1)

        # --- Buttons -------------------------------------------------
        button_layout = QHBoxLayout()
        large_button_style = "font-size: 12pt;"

        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet(large_button_style)
        self.reset_button.setObjectName("reset_button")

        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setStyleSheet(f"{large_button_style} font-weight: bold;")
        self.calculate_button.setObjectName("calculate_button")
        self.calculate_button.setEnabled(False)

        button_layout.addStretch(1)
        button_layout.addWidget(self.reset_button)
        button_layout.addWidget(self.calculate_button)
        layout.addLayout(button_layout)

        return frame

    def _create_result_widget(self) -> QFrame:
        frame  = QFrame()
        layout = QVBoxLayout(frame)

        self.result_label = QLabel("Result...")
        self.result_label.setObjectName("result_label")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        result_font = QFont(); result_font.setBold(True); result_font.setPointSize(18)
        self.result_label.setFont(result_font)
        layout.addWidget(self.result_label)
        return frame

    # ==================================================================
    # Slots
    # ==================================================================

    def _on_calibration_mode_toggled(self, enabled: bool) -> None:
        """Expands or collapses the calibration-mode section."""
        self.calibration_mode_frame.setVisible(enabled)
        if not enabled:
            # Clear the fields so disabled + non-zero values don't
            # accidentally tag a later measurement.
            self.reference_thickness_spin.blockSignals(True)
            self.session_tag_field.blockSignals(True)
            self.reference_thickness_spin.setValue(self.REF_NM_DEFAULT)
            self.session_tag_field.setText("")
            self.reference_thickness_spin.blockSignals(False)
            self.session_tag_field.blockSignals(False)
        self.config_changed.emit()

    # ==================================================================
    # Public API used by MainController
    # ==================================================================

    def get_frame_count(self) -> int:
        return int(self.frame_count_spinbox.value())

    def get_measurement_data(self) -> dict[str, Any]:
        """
        Bundles all UI inputs for the controller.

        New in Step 8: `reference_thickness_nm` (None when not set / 0)
        and `session_tag` (None when empty).  The controller merges
        non-None values into the DB save payload.
        """
        ref_nm = float(self.reference_thickness_spin.value())
        if ref_nm <= 0:
            ref_nm_out: float | None = None
        else:
            ref_nm_out = ref_nm

        tag = self.session_tag_field.text().strip()
        tag_out: str | None = tag if tag else None

        return {
            "ref_capture":           self.reference_capture,
            "mat_capture":           self.material_capture,
            "frame_count":           self.get_frame_count(),
            "material_path":         self.material_selector.get_selected_path(),
            "wavelength_um":         self.wavelength_combo.currentData(),
            "save_checked":          self.save_measurement_checkbox.isChecked(),
            "use_name":              self.use_name_checkbox.isChecked(),
            "name":                  self.name_field.text(),
            "note":                  self.note_field.text(),
            "reference_thickness_nm": ref_nm_out,
            "session_tag":            tag_out,
        }

    def set_capture(
        self, capture: "FrameCaptureResult", image_type: str,
    ) -> None:
        if capture is None:
            return

        pixmap = self._convert_np_to_pixmap(capture.image)
        if image_type == "reference":
            self.reference_capture = capture
            target_label = self.ref_image_label; stats_label = self.ref_stats_label
        elif image_type == "material":
            self.material_capture = capture
            target_label = self.mat_image_label; stats_label = self.mat_stats_label
        else:
            logger.warning("set_capture: unknown image_type '%s'", image_type)
            return

        scaled_pixmap = pixmap.scaled(
            target_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        target_label.setPixmap(scaled_pixmap)
        stats_label.setText(self._format_capture_stats(capture))

    def reset_all(self):
        # Image previews
        self.reference_capture = None
        self.material_capture  = None
        for label in (self.ref_image_label, self.mat_image_label):
            label.clear(); label.setText("Image Preview")
            label.setStyleSheet("background-color: #2E2E2E; color: white; border: 1px solid #555;")
        self.ref_stats_label.setText(""); self.mat_stats_label.setText("")

        # Config widgets (block signals during programmatic reset)
        widgets_to_block = (
            self.wavelength_combo, self.frame_count_spinbox,
            self.use_name_checkbox, self.name_field,
            self.save_measurement_checkbox, self.note_field,
            self.calibration_mode_checkbox, self.reference_thickness_spin,
            self.session_tag_field,
        )
        for w in widgets_to_block: w.blockSignals(True)

        self.wavelength_combo.setCurrentIndex(0)
        self.frame_count_spinbox.setValue(self.FRAME_COUNT_DEFAULT)
        self.use_name_checkbox.setChecked(False)
        self.name_field.setText("")
        self.save_measurement_checkbox.setChecked(True)
        self.note_field.setText("")
        self.calibration_mode_checkbox.setChecked(False)
        self.reference_thickness_spin.setValue(self.REF_NM_DEFAULT)
        self.session_tag_field.setText("")
        self.calibration_mode_frame.setVisible(False)
        self.calculate_button.setEnabled(False)

        for w in widgets_to_block: w.blockSignals(False)

        if hasattr(self, "material_selector"):
            self.material_selector.page_combo.blockSignals(True)
            self.material_selector._populate_shelves()
            self.material_selector.page_combo.blockSignals(False)

        self.set_result_text("Result...")

    def populate_material_selector(self, data: dict[str, Any]):
        if hasattr(self, "material_selector"):
            self.material_selector.populate_data(data)

    def set_result_text(self, text: str, append: bool = False):
        if not hasattr(self, "result_label"):
            return
        if append:
            current = self.result_label.text()
            if "Saved!" not in current:
                self.result_label.setText(f"{current}<br>Saved!")
        else:
            self.result_label.setText(text)

    def set_calculation_enabled(self, enabled: bool):
        self.calculate_button.setEnabled(enabled)

    def show_info_bar(
        self,
        title:      str,
        content:    str,
        is_error:   bool = False,
        is_warning: bool = False,
        duration:   int  = 3000,
    ):
        if is_error:
            InfoBar.error(
                title=title, content=content, duration=max(duration, 5000),
                parent=self, position=InfoBarPosition.TOP,
            )
        elif is_warning:
            InfoBar.warning(
                title=title, content=content, duration=max(duration, 4000),
                parent=self, position=InfoBarPosition.TOP,
            )
        else:
            InfoBar.success(
                title=title, content=content, duration=duration,
                parent=self, position=InfoBarPosition.TOP,
            )

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _format_capture_stats(capture: "FrameCaptureResult") -> str:
        if capture.frame_count == 1:
            return f"n=1 • μ={capture.gray_mean:.2f}"
        return (
            f"n={capture.frames_used}/{capture.frame_count}"
            f" • σ={capture.gray_std:.2f}"
            f" • μ={capture.gray_mean:.2f}"
            f" • outliers: {capture.outliers_rejected}"
        )

    def _convert_np_to_pixmap(self, image_array: np.ndarray | None) -> QPixmap:
        if image_array is None:
            return QPixmap()
        try:
            if image_array.ndim != 3:
                logger.error("Error converting image: expected 3 dims, got %s", image_array.ndim)
                return QPixmap()
            height, width, channels = image_array.shape
            if channels != 3:
                logger.error("Error converting image: expected 3 channels, got %s", channels)
                return QPixmap()
            stride = image_array.strides[0]
            q_image = QImage(
                image_array.data, width, height, stride, QImage.Format.Format_BGR888
            ).copy()
            return QPixmap.fromImage(q_image)
        except Exception as e:
            logger.error("Error converting image: %s", e)
            return QPixmap()