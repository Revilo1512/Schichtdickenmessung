from __future__ import annotations

import re
import logging
from typing import Any, TYPE_CHECKING

import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QComboBox, QVBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QCheckBox, QHBoxLayout,
    QSpinBox, QDoubleSpinBox, QGridLayout,
)
from PyQt6.QtGui  import (
    QStandardItemModel, QStandardItem, QFont, QPixmap, QImage, QShortcut,
    QKeySequence,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from qfluentwidgets import InfoBar, InfoBarPosition

from layer_thickness_app.config.config import AppConfig

if TYPE_CHECKING:
    from layer_thickness_app.services.camera_service import FrameCaptureResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MaterialSelector
# ---------------------------------------------------------------------------
class MaterialSelector(QFrame):
    """
    Three-cascading-combobox selector over the refractiveindex.info
    catalog. Emits `selection_changed(str | None)` whenever the full
    shelf/book/page path becomes valid or invalid.
    """

    selection_changed = pyqtSignal(object)   # str | None

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

        self.divider_font = QFont(); self.divider_font.setItalic(True); self.divider_font.setBold(True)
        self.header_font  = QFont(); self.header_font.setBold(True);    self.header_font.setPointSize(10)

        shelf_label = QLabel("Shelf (Category):"); shelf_label.setFont(self.header_font)
        book_label  = QLabel("Book (Material):");  book_label.setFont(self.header_font)
        page_label  = QLabel("Page (Dataset):");   page_label.setFont(self.header_font)

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(shelf_label); layout.addWidget(self.shelf_combo)
        layout.addWidget(book_label);  layout.addWidget(self.book_combo)
        layout.addWidget(page_label);  layout.addWidget(self.page_combo)
        self.setLayout(layout)

        self.shelf_combo.currentIndexChanged.connect(self._on_shelf_changed)
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)
        self.page_combo.currentIndexChanged.connect(self._emit_selection)

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

    def _emit_selection(self, _=None):
        self.selection_changed.emit(self.get_selected_path())

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
    Measurement capture page.

    Features wired through to the controller:
      - Material / wavelength / frame-count / name / note / save
      - Calibration-mode section with Reference Thickness and Session Tag
      - Probe and Run index fields for campaign runs
      - Batch mode: holds reference + metadata and auto-saves N samples
      - Keyboard shortcuts: R = reference, S = sample, Enter = calculate,
        Ctrl+S = toggle save
      - Real-time gray-mean readout (live preview updates when connected)
      - "Keep reference" lock so reset only clears the sample preview
    """

    config_changed              = pyqtSignal()
    calculation_requested       = pyqtSignal()
    capture_reference_requested = pyqtSignal()
    capture_material_requested  = pyqtSignal()
    reset_requested             = pyqtSignal()
    material_changed            = pyqtSignal(object)   # str | None
    batch_sample_requested      = pyqtSignal()         # batch-mode sample capture

    FRAME_COUNT_MIN     = 1
    FRAME_COUNT_MAX     = 100
    FRAME_COUNT_DEFAULT = AppConfig.FRAME_COUNT_DEFAULT

    # Reference-thickness input bounds (nm). 0 = "not set".
    REF_NM_MIN:     float = 0.0
    REF_NM_MAX:     float = 5000.0
    REF_NM_DEFAULT: float = 0.0

    # Batch-mode defaults
    BATCH_RUNS_DEFAULT = 25
    BATCH_RUNS_MIN     = 1
    BATCH_RUNS_MAX     = 500

    def __init__(self):
        super().__init__()
        self.setObjectName("measurePage")
        self.setWindowTitle("Measurement Tool")

        self.reference_capture: "FrameCaptureResult | None" = None
        self.material_capture:  "FrameCaptureResult | None" = None

        # Batch state
        self._batch_active:        bool = False
        self._batch_current_run:   int  = 0
        self._batch_total_runs:    int  = 0

        # Widget references (set during _build_ui)
        self.ref_image_button: QPushButton
        self.mat_image_button: QPushButton
        self.ref_image_label:  QLabel
        self.mat_image_label:  QLabel
        self.ref_stats_label:  QLabel
        self.mat_stats_label:  QLabel
        self.ref_live_label:   QLabel
        self.mat_live_label:   QLabel

        self._build_ui()
        self._wire_shortcuts()

    # ==================================================================
    # Layout
    # ==================================================================

    def _build_ui(self):
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

        # Connect internal signals now that all widgets exist.
        self._connect_internal_signals()

    # ==================================================================
    # Widget builders
    # ==================================================================

    def _create_image_capture_widget(self, title: str, prefix: str) -> QFrame:
        """
        Build a capture panel. References to the child widgets are stored
        directly on self so we don't need findChild() later.
        """
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

        stats_label = QLabel("")
        stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_label.setFont(stats_font)
        stats_label.setStyleSheet("color: gray;")
        stats_label.setMinimumHeight(14)

        live_label = QLabel("")
        live_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        live_label.setFont(stats_font)
        live_label.setStyleSheet("color: #5a9bd4;")
        live_label.setMinimumHeight(14)

        capture_button = QPushButton(f"Take {title}")

        layout.addWidget(title_label)
        layout.addWidget(image_placeholder, 1)
        layout.addWidget(stats_label)
        layout.addWidget(live_label)
        layout.addWidget(capture_button)

        # Store direct references.
        if prefix == "reference_image":
            self.ref_image_label  = image_placeholder
            self.ref_stats_label  = stats_label
            self.ref_live_label   = live_label
            self.ref_image_button = capture_button
        else:
            self.mat_image_label  = image_placeholder
            self.mat_stats_label  = stats_label
            self.mat_live_label   = live_label
            self.mat_image_button = capture_button
        return frame

    def _create_config_and_selector_widget(self) -> QFrame:
        frame  = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        header_font = QFont(); header_font.setBold(True); header_font.setPointSize(10)
        hint_font   = QFont(); hint_font.setPointSize(8)

        # --- Material selector -------------------------
        self.material_selector = MaterialSelector()
        layout.addWidget(self.material_selector)

        # --- Profile caption (populated by controller) --
        self.profile_caption = QLabel("")
        self.profile_caption.setFont(hint_font)
        self.profile_caption.setStyleSheet("color: gray;")
        layout.addWidget(self.profile_caption)

        # --- Wavelength -------------------------------
        layout.addSpacing(10)
        wavelength_label = QLabel("Wavelength:"); wavelength_label.setFont(header_font)
        self.wavelength_combo = QComboBox()
        for label, value in AppConfig.WAVELENGTHS:
            self.wavelength_combo.addItem(label, value)
        layout.addWidget(wavelength_label)
        layout.addWidget(self.wavelength_combo)

        # --- Frame count ------------------------------
        layout.addSpacing(10)
        frame_count_label = QLabel("Frames per Capture:"); frame_count_label.setFont(header_font)
        self.frame_count_spinbox = QSpinBox()
        self.frame_count_spinbox.setRange(self.FRAME_COUNT_MIN, self.FRAME_COUNT_MAX)
        self.frame_count_spinbox.setValue(self.FRAME_COUNT_DEFAULT)
        self.frame_count_spinbox.setToolTip(
            "Number of frames to average per capture. 1 = single-frame mode. "
            "Recommended for calibration / MSA: 30."
        )
        frame_hint = QLabel("Higher = less noise, slower capture")
        frame_hint.setFont(hint_font); frame_hint.setStyleSheet("color: gray;")
        layout.addWidget(frame_count_label)
        layout.addWidget(self.frame_count_spinbox)
        layout.addWidget(frame_hint)

        # --- Calibration-mode section -----------------
        layout.addSpacing(10)
        self.calibration_mode_checkbox = QCheckBox("Calibration Mode")
        self.calibration_mode_checkbox.setFont(header_font)
        self.calibration_mode_checkbox.setToolTip(
            "Enable to tag measurements with a known Reference Thickness\n"
            "and a Session Tag — required to fit calibration models and\n"
            "run MSA Typ 1 validations."
        )
        layout.addWidget(self.calibration_mode_checkbox)

        self.calibration_mode_frame = QFrame()
        cal_grid = QGridLayout(self.calibration_mode_frame)
        cal_grid.setContentsMargins(0, 5, 0, 0); cal_grid.setSpacing(8)

        ref_label = QLabel("Reference:"); ref_label.setFont(header_font)
        self.reference_thickness_spin = QDoubleSpinBox()
        self.reference_thickness_spin.setRange(self.REF_NM_MIN, self.REF_NM_MAX)
        self.reference_thickness_spin.setDecimals(2)
        self.reference_thickness_spin.setSingleStep(1.0)
        self.reference_thickness_spin.setValue(self.REF_NM_DEFAULT)
        self.reference_thickness_spin.setSuffix(" nm")
        self.reference_thickness_spin.setSpecialValueText("— not set —")

        session_label = QLabel("Session tag:"); session_label.setFont(header_font)
        self.session_tag_field = QLineEdit()
        self.session_tag_field.setPlaceholderText("e.g. Cu_linearity_2026-04-25")

        probe_label = QLabel("Probe:"); probe_label.setFont(header_font)
        self.probe_field = QLineEdit()
        self.probe_field.setPlaceholderText("e.g. Cu_P1")

        run_label = QLabel("Run idx:"); run_label.setFont(header_font)
        self.run_index_spin = QSpinBox()
        self.run_index_spin.setRange(0, 10_000)
        self.run_index_spin.setSpecialValueText("— auto —")
        self.run_index_spin.setValue(0)
        self.run_index_spin.setToolTip(
            "Optional run index. Leave at 0 for auto-increment in batch mode."
        )

        cal_grid.addWidget(ref_label,                     0, 0)
        cal_grid.addWidget(self.reference_thickness_spin, 0, 1)
        cal_grid.addWidget(session_label,                 1, 0)
        cal_grid.addWidget(self.session_tag_field,        1, 1)
        cal_grid.addWidget(probe_label,                   2, 0)
        cal_grid.addWidget(self.probe_field,              2, 1)
        cal_grid.addWidget(run_label,                     3, 0)
        cal_grid.addWidget(self.run_index_spin,           3, 1)
        cal_grid.setColumnStretch(1, 1)

        layout.addWidget(self.calibration_mode_frame)
        self.calibration_mode_frame.setVisible(False)

        # --- Batch mode --------------------------------
        layout.addSpacing(8)
        self.batch_mode_checkbox = QCheckBox("Batch Mode")
        self.batch_mode_checkbox.setFont(header_font)
        self.batch_mode_checkbox.setToolTip(
            "Hold reference and metadata constant; each Sample capture\n"
            "auto-saves and auto-increments the Run index."
        )
        layout.addWidget(self.batch_mode_checkbox)

        self.batch_frame = QFrame()
        batch_grid = QGridLayout(self.batch_frame)
        batch_grid.setContentsMargins(0, 5, 0, 0); batch_grid.setSpacing(8)

        runs_label = QLabel("Runs per probe:"); runs_label.setFont(header_font)
        self.batch_runs_spin = QSpinBox()
        self.batch_runs_spin.setRange(self.BATCH_RUNS_MIN, self.BATCH_RUNS_MAX)
        self.batch_runs_spin.setValue(self.BATCH_RUNS_DEFAULT)

        self.batch_progress_label = QLabel("Batch inactive")
        self.batch_progress_label.setFont(hint_font)
        self.batch_progress_label.setStyleSheet("color: gray;")

        batch_grid.addWidget(runs_label,                0, 0)
        batch_grid.addWidget(self.batch_runs_spin,      0, 1)
        batch_grid.addWidget(self.batch_progress_label, 1, 0, 1, 2)
        batch_grid.setColumnStretch(1, 1)

        layout.addWidget(self.batch_frame)
        self.batch_frame.setVisible(False)

        # --- Keep reference lock -----------------------
        layout.addSpacing(4)
        self.keep_reference_checkbox = QCheckBox("Keep reference on reset")
        self.keep_reference_checkbox.setToolTip(
            "When checked, Reset clears only the sample preview and the "
            "reference capture is preserved."
        )
        layout.addWidget(self.keep_reference_checkbox)

        # --- Name -------------------------------------
        layout.addSpacing(10)
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Guest")
        self.name_field.setEnabled(False)
        self.use_name_checkbox = QCheckBox("Name:")
        self.use_name_checkbox.setFont(header_font)
        self.use_name_checkbox.toggled.connect(self.name_field.setEnabled)

        name_row = QHBoxLayout()
        name_row.addWidget(self.use_name_checkbox)
        name_row.addWidget(self.name_field)
        layout.addLayout(name_row)

        # --- Save checkbox ----------------------------
        layout.addSpacing(8)
        self.save_measurement_checkbox = QCheckBox("Save Measurement?")
        self.save_measurement_checkbox.setChecked(True)
        self.save_measurement_checkbox.setFont(header_font)
        layout.addWidget(self.save_measurement_checkbox)

        # --- Note -------------------------------------
        layout.addSpacing(8)
        note_label = QLabel("Note:"); note_label.setFont(header_font)
        self.note_field = QLineEdit()
        self.note_field.setPlaceholderText("Optional note...")
        layout.addWidget(note_label)
        layout.addWidget(self.note_field)

        layout.addStretch(1)

        # --- Buttons ----------------------------------
        button_row = QHBoxLayout()
        large_style = "font-size: 12pt;"

        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet(large_style)

        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setStyleSheet(f"{large_style} font-weight: bold;")
        self.calculate_button.setEnabled(False)

        button_row.addStretch(1)
        button_row.addWidget(self.reset_button)
        button_row.addWidget(self.calculate_button)
        layout.addLayout(button_row)

        return frame

    def _create_result_widget(self) -> QFrame:
        frame  = QFrame()
        layout = QVBoxLayout(frame)

        self.result_label = QLabel("Result...")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        result_font = QFont(); result_font.setBold(True); result_font.setPointSize(18)
        self.result_label.setFont(result_font)
        layout.addWidget(self.result_label)
        return frame

    # ==================================================================
    # Signal wiring
    # ==================================================================

    def _connect_internal_signals(self):
        self.calculate_button.clicked.connect(self.calculation_requested.emit)
        self.ref_image_button.clicked.connect(self.capture_reference_requested.emit)
        self.mat_image_button.clicked.connect(self._on_sample_button_clicked)
        self.reset_button.clicked.connect(self.reset_requested.emit)

        # Config-change signals
        self.material_selector.selection_changed.connect(self._on_material_changed)
        self.material_selector.selection_changed.connect(
            lambda _: self.config_changed.emit()
        )
        self.wavelength_combo.currentIndexChanged.connect(self.config_changed.emit)
        self.frame_count_spinbox.valueChanged.connect(self.config_changed.emit)
        self.reference_thickness_spin.valueChanged.connect(self.config_changed.emit)
        self.session_tag_field.textChanged.connect(self.config_changed.emit)
        self.probe_field.textChanged.connect(self.config_changed.emit)
        self.run_index_spin.valueChanged.connect(self.config_changed.emit)
        self.name_field.textChanged.connect(self.config_changed.emit)
        self.use_name_checkbox.toggled.connect(self.config_changed.emit)
        self.save_measurement_checkbox.toggled.connect(self.config_changed.emit)
        self.note_field.textChanged.connect(self.config_changed.emit)

        # Section toggles
        self.calibration_mode_checkbox.toggled.connect(self._on_calibration_mode_toggled)
        self.batch_mode_checkbox.toggled.connect(self._on_batch_mode_toggled)

    def _wire_shortcuts(self):
        """R = reference, S = sample, Enter = calculate, Ctrl+S = toggle save."""
        def make_shortcut(seq: str, slot):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(slot)
            return sc

        make_shortcut("R",       self.ref_image_button.click)
        make_shortcut("S",       self._on_sample_button_clicked)
        make_shortcut("Return",  self._shortcut_calculate)
        make_shortcut("Enter",   self._shortcut_calculate)
        make_shortcut("Ctrl+S",  self._shortcut_toggle_save)

    def _shortcut_calculate(self):
        if self.calculate_button.isEnabled():
            self.calculate_button.click()

    def _shortcut_toggle_save(self):
        self.save_measurement_checkbox.setChecked(
            not self.save_measurement_checkbox.isChecked()
        )

    def _on_material_changed(self, path):
        self.material_changed.emit(path)

    def _on_sample_button_clicked(self):
        """In batch mode, a sample capture runs through the batch flow."""
        if self._batch_active:
            self.batch_sample_requested.emit()
        else:
            self.capture_material_requested.emit()

    def _on_calibration_mode_toggled(self, enabled: bool):
        self.calibration_mode_frame.setVisible(enabled)
        if not enabled:
            # Clear the fields so disabled + non-zero values don't
            # accidentally tag a later measurement.
            for w in (
                self.reference_thickness_spin, self.session_tag_field,
                self.probe_field, self.run_index_spin,
            ):
                w.blockSignals(True)
            self.reference_thickness_spin.setValue(self.REF_NM_DEFAULT)
            self.session_tag_field.setText("")
            self.probe_field.setText("")
            self.run_index_spin.setValue(0)
            for w in (
                self.reference_thickness_spin, self.session_tag_field,
                self.probe_field, self.run_index_spin,
            ):
                w.blockSignals(False)
            # Batch mode requires calibration mode — disable it too.
            if self.batch_mode_checkbox.isChecked():
                self.batch_mode_checkbox.setChecked(False)
        self.config_changed.emit()

    def _on_batch_mode_toggled(self, enabled: bool):
        """Batch mode requires calibration mode to provide probe/session/ref."""
        if enabled and not self.calibration_mode_checkbox.isChecked():
            self.show_info_bar(
                "Enable Calibration Mode",
                "Batch mode needs a Reference Thickness, Session Tag "
                "and Probe — please enable Calibration Mode first.",
                is_warning=True,
            )
            self.batch_mode_checkbox.blockSignals(True)
            self.batch_mode_checkbox.setChecked(False)
            self.batch_mode_checkbox.blockSignals(False)
            return
        self.batch_frame.setVisible(enabled)
        if not enabled:
            self._batch_active      = False
            self._batch_current_run = 0
            self._batch_total_runs  = 0
            self.batch_progress_label.setText("Batch inactive")

    # ==================================================================
    # Public API used by MainController
    # ==================================================================

    def get_frame_count(self) -> int:
        return int(self.frame_count_spinbox.value())

    def get_measurement_data(self) -> dict[str, Any]:
        ref_nm: float | None = float(self.reference_thickness_spin.value())
        if ref_nm is not None and ref_nm <= 0:
            ref_nm = None

        tag = self.session_tag_field.text().strip()
        probe = self.probe_field.text().strip()
        run = int(self.run_index_spin.value())
        run_out = run if run > 0 else None

        return {
            "ref_capture":            self.reference_capture,
            "mat_capture":            self.material_capture,
            "frame_count":            self.get_frame_count(),
            "material_path":          self.material_selector.get_selected_path(),
            "wavelength_um":          self.wavelength_combo.currentData(),
            "save_checked":           self.save_measurement_checkbox.isChecked(),
            "use_name":               self.use_name_checkbox.isChecked(),
            "name":                   self.name_field.text(),
            "note":                   self.note_field.text(),
            "reference_thickness_nm": ref_nm,
            "session_tag":            tag if tag else None,
            "probe":                  probe if probe else None,
            "run_index":              run_out,
            "batch_mode":             self._batch_active,
        }

    def set_capture(self, capture: "FrameCaptureResult", image_type: str) -> None:
        if capture is None:
            return
        pixmap = self._convert_np_to_pixmap(capture.image)
        if image_type == "reference":
            self.reference_capture = capture
            target_label = self.ref_image_label
            stats_label  = self.ref_stats_label
        elif image_type == "material":
            self.material_capture = capture
            target_label = self.mat_image_label
            stats_label  = self.mat_stats_label
        else:
            logger.warning("set_capture: unknown image_type '%s'", image_type)
            return

        scaled = pixmap.scaled(
            target_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        target_label.setPixmap(scaled)
        stats_label.setText(self._format_capture_stats(capture))

    def set_live_gray(self, ref_gray: float | None, mat_gray: float | None):
        """
        Update the per-preview live gray readout (used by the controller's
        2 Hz timer while the operator aligns the probe).
        """
        if ref_gray is not None:
            self.ref_live_label.setText(f"live μ={ref_gray:.2f}")
        else:
            self.ref_live_label.setText("")
        if mat_gray is not None:
            self.mat_live_label.setText(f"live μ={mat_gray:.2f}")
        else:
            self.mat_live_label.setText("")

    def set_profile_caption(self, text: str):
        self.profile_caption.setText(text)

    def set_reference_thickness_hint(self, lo: float | None, hi: float | None):
        """Update the Reference-Thickness range hint based on the profile."""
        if lo is None or hi is None:
            self.reference_thickness_spin.setToolTip(
                "Known true thickness of the sample, in nanometres.\n"
                "Set to 0 to leave blank."
            )
            return
        self.reference_thickness_spin.setToolTip(
            f"Known true thickness of the sample, in nanometres.\n"
            f"Expected range for this material: {lo:g} – {hi:g} nm."
        )

    # -- Batch-mode API -----------------------------------------------

    def batch_is_active(self) -> bool:
        return self._batch_active

    def batch_start(self, total_runs: int):
        self._batch_active      = True
        self._batch_current_run = 0
        self._batch_total_runs  = total_runs

    def batch_advance(self):
        """Bump the run counter after a successful sample save."""
        self._batch_current_run += 1
        self.run_index_spin.setValue(self._batch_current_run)
        probe = self.probe_field.text().strip() or "—"
        self.batch_progress_label.setText(
            f"Probe {probe} — Run {self._batch_current_run} of {self._batch_total_runs}"
        )

    def batch_finish(self):
        self._batch_active = False
        self.batch_progress_label.setText(
            f"Batch complete: {self._batch_current_run} runs captured."
        )

    def batch_runs_configured(self) -> int:
        return int(self.batch_runs_spin.value())

    def batch_current_run(self) -> int:
        return self._batch_current_run

    def batch_total_runs(self) -> int:
        return self._batch_total_runs

    # -- Reset / state -----------------------------------------------

    def reset_all(self):
        """
        Full reset. If the "Keep reference on reset" checkbox is set,
        the reference capture and its preview are preserved.
        """
        keep_ref = self.keep_reference_checkbox.isChecked()

        if not keep_ref:
            self.reference_capture = None
            self.ref_image_label.clear()
            self.ref_image_label.setText("Image Preview")
            self.ref_image_label.setStyleSheet(
                "background-color: #2E2E2E; color: white; border: 1px solid #555;"
            )
            self.ref_stats_label.setText("")

        # Always clear the sample preview.
        self.material_capture = None
        self.mat_image_label.clear()
        self.mat_image_label.setText("Image Preview")
        self.mat_image_label.setStyleSheet(
            "background-color: #2E2E2E; color: white; border: 1px solid #555;"
        )
        self.mat_stats_label.setText("")

        # In batch mode we preserve session metadata too — a reset
        # between sample captures is common and must not wipe probe/tag.
        if not self._batch_active and not keep_ref:
            widgets_to_block = (
                self.wavelength_combo, self.frame_count_spinbox,
                self.use_name_checkbox, self.name_field,
                self.save_measurement_checkbox, self.note_field,
                self.calibration_mode_checkbox, self.reference_thickness_spin,
                self.session_tag_field, self.probe_field, self.run_index_spin,
                self.batch_mode_checkbox, self.batch_runs_spin,
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
            self.probe_field.setText("")
            self.run_index_spin.setValue(0)
            self.calibration_mode_frame.setVisible(False)
            self.batch_mode_checkbox.setChecked(False)
            self.batch_runs_spin.setValue(self.BATCH_RUNS_DEFAULT)
            self.batch_frame.setVisible(False)

            for w in widgets_to_block: w.blockSignals(False)

            if hasattr(self, "material_selector"):
                self.material_selector.page_combo.blockSignals(True)
                self.material_selector._populate_shelves()
                self.material_selector.page_combo.blockSignals(False)

        self.calculate_button.setEnabled(False)
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
                image_array.data, width, height, stride, QImage.Format.Format_BGR888,
            ).copy()
            return QPixmap.fromImage(q_image)
        except Exception as e:
            logger.error("Error converting image: %s", e)
            return QPixmap()