"""
Calibration Page — fit, evaluate and activate linear correction models.

Workflow
--------
1.  Select material (Book + Page), wavelength and mode.
2.  The page pulls all measurements with that (Book, Page, Wavelength,
    Mode) that also carry a ReferenceThickness — the calibration
    candidate rows.
3.  A table lets the user mark each row as train / test / ignored.
    Quick actions provide sensible defaults:
      - "All train"           – everything contributes to the fit.
      - "Random 70/30"        – random split (seeded).
      - "Hold out <ref>"      – drop all rows at a specific reference
                                thickness into test.
4.  "Fit Model" runs least-squares on the train rows and evaluates on
    the test rows. Slope / intercept / R² and the before/after
    statistics (bias, MAE, RMSE) are shown.
5.  "Save & Activate" persists the model and flags it active for
    measurement-time correction.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QComboBox,
)
from qfluentwidgets import (
    BodyLabel, SubtitleLabel, StrongBodyLabel, CaptionLabel,
    PushButton, PrimaryPushButton, ComboBox, LineEdit,
    TableWidget, InfoBar, InfoBarPosition, MessageBox, FluentIcon,
)

from layer_thickness_app.services.database_service    import DatabaseService
from layer_thickness_app.services.calibration_service import (
    CalibrationService, CalibrationModel,
)
from layer_thickness_app.gui.theme import (
    card_style, borderless_style, quality_color, FlowLayout,
    COLOR_SUCCESS, COLOR_ERROR,
)

logger = logging.getLogger(__name__)

ASSIGN_IGNORE = "ignore"
ASSIGN_TRAIN  = "train"
ASSIGN_TEST   = "test"

_ASSIGN_OPTIONS = [ASSIGN_IGNORE, ASSIGN_TRAIN, ASSIGN_TEST]

_COL_ID      = 0
_COL_DATE    = 1
_COL_REF     = 2
_COL_LAYER   = 3
_COL_MODE    = 4
_COL_FRAMES  = 5
_COL_SESSION = 6
_COL_ASSIGN  = 7

_FIT_PANEL_OBJECT_NAME = "calibration_fit_panel"


class CalibrationPage(QWidget):
    """Calibration workflow page."""

    calibration_activated = pyqtSignal(int)

    def __init__(
        self,
        db_service:          DatabaseService,
        calibration_service: CalibrationService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("calibrationPage")

        self.db_service          = db_service
        self.calibration_service = calibration_service

        self._rows: list[dict[str, Any]] = []
        self._current_model: CalibrationModel | None = None

        self._build_ui()
        self._connect_signals()
        self._refresh_filter_options()

    # ==================================================================
    # Layout
    # ==================================================================

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(15)

        root.addWidget(SubtitleLabel("Calibration — Fit Regression Model"))

        # Filter bar (FlowLayout wraps to a second row at narrow widths)
        self.book_combo   = ComboBox(self); self.book_combo.setPlaceholderText("Material (Book)")
        self.page_combo   = ComboBox(self); self.page_combo.setPlaceholderText("Dataset (Page)")
        self.wave_combo   = ComboBox(self)
        self.wave_combo.addItem("Red (635 nm)", None,   0.635)
        self.wave_combo.addItem("Green (532 nm)", None, 0.532)
        self.mode_combo   = ComboBox(self)
        self.mode_combo.addItems(["multi", "single"])
        self.session_combo = ComboBox(self); self.session_combo.setPlaceholderText("Any session")

        self.load_button = PushButton("Load Candidates", self)
        self.load_button.setIcon(FluentIcon.SYNC)

        filter_host = QWidget(self)
        flow = FlowLayout(filter_host, margin=0, h_spacing=10, v_spacing=8)
        for label, widget in (
            ("Book:",       self.book_combo),
            ("Page:",       self.page_combo),
            ("Wavelength:", self.wave_combo),
            ("Mode:",       self.mode_combo),
            ("Session:",    self.session_combo),
        ):
            flow.addWidget(self._make_field(label, widget))
        flow.addWidget(self.load_button)

        root.addWidget(filter_host)

        # Quick-action bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        self.all_train_button    = PushButton("All train", self)
        self.random_split_button = PushButton("Random 70/30", self)
        self.holdout_combo       = ComboBox(self)
        self.holdout_combo.setPlaceholderText("Hold out ref...")
        self.holdout_button      = PushButton("Hold out", self)
        self.clear_button        = PushButton("Clear assignments", self)

        action_bar.addWidget(StrongBodyLabel("Quick actions:"))
        action_bar.addWidget(self.all_train_button)
        action_bar.addWidget(self.random_split_button)
        action_bar.addWidget(self.holdout_combo)
        action_bar.addWidget(self.holdout_button)
        action_bar.addSpacing(10)
        action_bar.addWidget(self.clear_button)
        action_bar.addStretch(1)

        self.counts_label = CaptionLabel("Train: 0 · Test: 0 · Ignored: 0", self)
        action_bar.addWidget(self.counts_label)

        root.addLayout(action_bar)

        # Table
        self.table = TableWidget(self)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Date", "Ref (nm)", "Layer (nm)",
            "Mode", "Frames", "Session", "Role",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_SESSION, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(_COL_ID,     60)
        self.table.setColumnWidth(_COL_DATE,   140)
        self.table.setColumnWidth(_COL_REF,    90)
        self.table.setColumnWidth(_COL_LAYER,  100)
        self.table.setColumnWidth(_COL_MODE,   70)
        self.table.setColumnWidth(_COL_FRAMES, 70)
        self.table.setColumnWidth(_COL_ASSIGN, 100)

        root.addWidget(self.table, 1)

        # Fit result panel
        self.fit_panel = self._build_fit_panel()
        root.addWidget(self.fit_panel)

        # Save bar
        save_bar = QHBoxLayout()
        save_bar.setSpacing(10)

        self.name_field  = LineEdit(self); self.name_field.setPlaceholderText("Name (optional, e.g. 'Cu multi v1')")
        self.note_field  = LineEdit(self); self.note_field.setPlaceholderText("Note (optional)")
        self.fit_button  = PrimaryPushButton("Fit Model", self)
        self.save_button = PrimaryPushButton("Save & Activate", self)
        self.save_button.setEnabled(False)

        save_bar.addWidget(BodyLabel("Name:"))
        save_bar.addWidget(self.name_field, 1)
        save_bar.addWidget(BodyLabel("Note:"))
        save_bar.addWidget(self.note_field, 1)
        save_bar.addWidget(self.fit_button)
        save_bar.addWidget(self.save_button)
        root.addLayout(save_bar)

    @staticmethod
    def _make_field(label_text: str, widget: QWidget) -> QWidget:
        """
        Bundle a small caption + control into one widget so a flow layout
        can keep them together when wrapping to a new row.
        """
        host = QWidget()
        h = QHBoxLayout(host)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(BodyLabel(label_text))
        h.addWidget(widget)
        return host

    def _build_fit_panel(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName(_FIT_PANEL_OBJECT_NAME)
        frame.setStyleSheet(card_style(_FIT_PANEL_OBJECT_NAME))

        outer = QHBoxLayout(frame)
        outer.setContentsMargins(20, 15, 20, 15)
        outer.setSpacing(30)

        # Left: model parameters
        left_form = QFormLayout()
        left_form.setSpacing(8)
        self.lbl_slope     = BodyLabel("—")
        self.lbl_intercept = BodyLabel("—")
        self.lbl_r2        = BodyLabel("—")
        self.lbl_nsamples  = BodyLabel("—")
        self.lbl_range     = BodyLabel("—")
        for lbl in (self.lbl_slope, self.lbl_intercept, self.lbl_r2,
                    self.lbl_nsamples, self.lbl_range):
            lbl.setStyleSheet(borderless_style())

        left_form.addRow(StrongBodyLabel("Slope (β₁):"),     self.lbl_slope)
        left_form.addRow(StrongBodyLabel("Intercept (β₀):"), self.lbl_intercept)
        left_form.addRow(StrongBodyLabel("R²:"),             self.lbl_r2)
        left_form.addRow(StrongBodyLabel("Train n:"),        self.lbl_nsamples)
        left_form.addRow(StrongBodyLabel("Fitted range:"),   self.lbl_range)

        # Right: test-set metrics (before vs after)
        right_form = QFormLayout()
        right_form.setSpacing(8)
        self.lbl_test_n    = BodyLabel("—")
        self.lbl_mean_bias = BodyLabel("—")
        self.lbl_mae       = BodyLabel("—")
        self.lbl_rmse      = BodyLabel("—")
        self.lbl_max_err   = BodyLabel("—")
        for lbl in (self.lbl_test_n, self.lbl_mean_bias, self.lbl_mae,
                    self.lbl_rmse, self.lbl_max_err):
            lbl.setStyleSheet(borderless_style())

        right_form.addRow(StrongBodyLabel("Test n:"),                  self.lbl_test_n)
        right_form.addRow(StrongBodyLabel("Mean bias (raw → corr):"),  self.lbl_mean_bias)
        right_form.addRow(StrongBodyLabel("MAE  (raw → corr):"),       self.lbl_mae)
        right_form.addRow(StrongBodyLabel("RMSE (raw → corr):"),       self.lbl_rmse)
        right_form.addRow(StrongBodyLabel("Max |err| (raw → corr):"),  self.lbl_max_err)

        outer.addLayout(left_form,  1)
        outer.addLayout(right_form, 1)
        return frame

    # ==================================================================
    # Signal wiring
    # ==================================================================

    def _connect_signals(self) -> None:
        self.load_button.clicked.connect(self._on_load_candidates)
        self.book_combo.currentTextChanged.connect(self._on_book_changed)

        self.all_train_button.clicked.connect(self._on_all_train)
        self.random_split_button.clicked.connect(self._on_random_split)
        self.holdout_button.clicked.connect(self._on_holdout)
        self.clear_button.clicked.connect(self._on_clear_assignments)

        self.fit_button.clicked.connect(self._on_fit)
        self.save_button.clicked.connect(self._on_save)

    # ==================================================================
    # Filter / loading
    # ==================================================================

    def _refresh_filter_options(self) -> None:
        self.book_combo.blockSignals(True)
        self.book_combo.clear()
        self.book_combo.addItems(self.db_service.get_unique_books())
        self.book_combo.setCurrentIndex(-1)
        self.book_combo.blockSignals(False)

        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        self.session_combo.addItem("")
        self.session_combo.addItems(self.db_service.get_unique_sessions())
        self.session_combo.setCurrentIndex(0)
        self.session_combo.blockSignals(False)

    def _on_book_changed(self, _text: str) -> None:
        book = self.book_combo.currentText()
        if not book:
            self.page_combo.clear()
            return

        pages = self.db_service.get_pages_for_book(book)
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        self.page_combo.addItems(pages)
        self.page_combo.setCurrentIndex(-1)
        self.page_combo.blockSignals(False)

    def _on_load_candidates(self) -> None:
        book = self.book_combo.currentText() or None
        page = self.page_combo.currentText() or None
        wavelength = self.wave_combo.currentData()
        mode = self.mode_combo.currentText() or None
        session = self.session_combo.currentText() or None

        if not book or not page:
            self._toast("Select a Book and Page first.", is_warning=True)
            return

        rows = self.db_service.get_calibration_rows(
            book=book, page=page, session_tag=session,
            wavelength_um=wavelength, mode=mode,
        )

        self._rows = rows
        self._populate_table(rows)

        refs = sorted({r["ReferenceThickness"] for r in rows
                       if r.get("ReferenceThickness") is not None})
        self.holdout_combo.blockSignals(True)
        self.holdout_combo.clear()
        for r in refs:
            self.holdout_combo.addItem(f"{r:g} nm", float(r))
        self.holdout_combo.setCurrentIndex(-1 if not refs else 0)
        self.holdout_combo.blockSignals(False)

        self._clear_fit_panel()
        self._current_model = None
        self.save_button.setEnabled(False)
        self._update_counts_label()

        logger.info("Loaded %d calibration candidates.", len(rows))
        if not rows:
            self._toast("No calibration rows match those filters.", is_warning=True)

    # ==================================================================
    # Table helpers
    # ==================================================================

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(rows))

            for i, r in enumerate(rows):
                def _item(text: str, align_center: bool = True) -> QTableWidgetItem:
                    it = QTableWidgetItem(text)
                    if align_center:
                        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    return it

                layer = r.get("Layer")
                ref   = r.get("ReferenceThickness")
                # The DB stores per-side counts; sample frames are what matter
                # for calibration noise.
                frames = r.get("FrameCountSample") or r.get("FrameCountRef")

                self.table.setItem(i, _COL_ID,      _item(str(r.get("id", ""))))
                self.table.setItem(i, _COL_DATE,    _item(str(r.get("Date", ""))[:19]))
                self.table.setItem(i, _COL_REF,     _item(f"{ref:g}"     if ref   is not None else "—"))
                self.table.setItem(i, _COL_LAYER,   _item(f"{layer:.3f}" if layer is not None else "—"))
                self.table.setItem(i, _COL_MODE,    _item(str(r.get("Mode", ""))))
                self.table.setItem(i, _COL_FRAMES,  _item(str(frames) if frames is not None else ""))
                self.table.setItem(i, _COL_SESSION, _item(str(r.get("SessionTag") or "")))

                combo = QComboBox()
                combo.addItems(_ASSIGN_OPTIONS)
                combo.setCurrentText(ASSIGN_IGNORE)
                combo.currentTextChanged.connect(self._update_counts_label)
                self.table.setCellWidget(i, _COL_ASSIGN, combo)
        finally:
            self.table.setUpdatesEnabled(True)

    def _get_assignment(self, row_idx: int) -> str:
        widget = self.table.cellWidget(row_idx, _COL_ASSIGN)
        return widget.currentText() if isinstance(widget, QComboBox) else ASSIGN_IGNORE

    def _set_assignment(self, row_idx: int, value: str) -> None:
        widget = self.table.cellWidget(row_idx, _COL_ASSIGN)
        if isinstance(widget, QComboBox):
            widget.setCurrentText(value)

    def _update_counts_label(self) -> None:
        n_train = n_test = n_ignore = 0
        for i in range(self.table.rowCount()):
            a = self._get_assignment(i)
            if   a == ASSIGN_TRAIN: n_train  += 1
            elif a == ASSIGN_TEST:  n_test   += 1
            else:                   n_ignore += 1
        self.counts_label.setText(
            f"Train: {n_train} · Test: {n_test} · Ignored: {n_ignore}"
        )

    # ==================================================================
    # Quick actions
    # ==================================================================

    def _on_all_train(self) -> None:
        for i in range(self.table.rowCount()):
            self._set_assignment(i, ASSIGN_TRAIN)
        self._update_counts_label()

    def _on_random_split(self) -> None:
        if not self._rows:
            self._toast("Load candidates first.", is_warning=True)
            return

        _, test_rows = self.calibration_service.split_by_measurement(
            self._rows, test_ratio=0.3,
        )
        test_ids = {r.get("id") for r in test_rows}
        for i, r in enumerate(self._rows):
            target = ASSIGN_TEST if r.get("id") in test_ids else ASSIGN_TRAIN
            self._set_assignment(i, target)
        self._update_counts_label()

    def _on_holdout(self) -> None:
        ref = self.holdout_combo.currentData()
        if ref is None:
            self._toast("Select a reference thickness in the 'Hold out' combo.",
                        is_warning=True)
            return

        _, test_rows = self.calibration_service.split_by_reference(
            self._rows, test_references=[float(ref)], tolerance=0.5,
        )
        test_ids = {r.get("id") for r in test_rows}
        for i, r in enumerate(self._rows):
            target = ASSIGN_TEST if r.get("id") in test_ids else ASSIGN_TRAIN
            self._set_assignment(i, target)
        self._update_counts_label()

    def _on_clear_assignments(self) -> None:
        for i in range(self.table.rowCount()):
            self._set_assignment(i, ASSIGN_IGNORE)
        self._update_counts_label()

    # ==================================================================
    # Fit / Save
    # ==================================================================

    def _collect_split(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        train: list[dict[str, Any]] = []
        test:  list[dict[str, Any]] = []
        for i, row in enumerate(self._rows):
            a = self._get_assignment(i)
            if   a == ASSIGN_TRAIN: train.append(row)
            elif a == ASSIGN_TEST:  test.append(row)
        return train, test

    def _on_fit(self) -> None:
        if not self._rows:
            self._toast("Load candidates first.", is_warning=True)
            return

        train_rows, test_rows = self._collect_split()

        if len(train_rows) < self.calibration_service.MIN_POINTS_FOR_FIT:
            self._toast(
                f"Need at least {self.calibration_service.MIN_POINTS_FOR_FIT} "
                f"training rows (got {len(train_rows)}).",
                is_warning=True,
            )
            return

        book = self.book_combo.currentText()
        page = self.page_combo.currentText()
        wavelength = float(self.wave_combo.currentData())
        mode = self.mode_combo.currentText()
        session = self.session_combo.currentText() or None

        shelf = train_rows[0].get("Shelf", "") or ""
        if not shelf:
            shelf = self.db_service.get_shelf_for_book_page(book, page) or ""

        try:
            model = self.calibration_service.fit_from_rows(
                train_rows, shelf=shelf, book=book, page=page,
                wavelength_um=wavelength, mode=mode,
                name=self.name_field.text(),
                session_tag=session,
                note=self.note_field.text(),
            )
        except Exception as e:
            logger.exception("Fit failed: %s", e)
            self._toast(f"Fit failed: {e}", is_error=True)
            return

        self._current_model = model
        self._render_fit_panel(model, test_rows)
        self.save_button.setEnabled(True)

    def _render_fit_panel(
        self,
        model: CalibrationModel,
        test_rows: list[dict[str, Any]],
    ) -> None:
        self.lbl_slope.setText(f"{model.slope:.6f}")
        self.lbl_intercept.setText(f"{model.intercept:.6f}")
        self.lbl_r2.setText(f"{model.r_squared:.4f}")
        self.lbl_nsamples.setText(str(model.n_samples))
        self.lbl_range.setText(f"{model.min_ref_nm:g} – {model.max_ref_nm:g} nm")

        self.lbl_r2.setStyleSheet(
            f"{borderless_style()} font-weight: bold; "
            f"color: {quality_color(model.r_squared)};"
        )

        if not test_rows:
            for lbl in (self.lbl_test_n, self.lbl_mean_bias,
                        self.lbl_mae, self.lbl_rmse, self.lbl_max_err):
                lbl.setText("— (no test rows)")
                lbl.setStyleSheet(borderless_style())
            return

        measured  = [r["Layer"]              for r in test_rows]
        reference = [r["ReferenceThickness"] for r in test_rows]

        try:
            metrics = self.calibration_service.evaluate(model, measured, reference)
        except Exception as e:
            logger.exception("Evaluation failed: %s", e)
            self._toast(f"Evaluation failed: {e}", is_error=True)
            return

        self.lbl_test_n.setText(str(metrics["n"]))

        def _arrow(before: float, after: float) -> tuple[str, str]:
            improved = abs(after) < abs(before)
            color = COLOR_SUCCESS if improved else COLOR_ERROR
            return f"{before:+.3f}  →  {after:+.3f} nm", color

        for label, before_k, after_k in (
            (self.lbl_mean_bias, "mean_bias_before",     "mean_bias_after"),
            (self.lbl_mae,       "mae_before",           "mae_after"),
            (self.lbl_rmse,      "rmse_before",          "rmse_after"),
            (self.lbl_max_err,   "max_abs_error_before", "max_abs_error_after"),
        ):
            text, color = _arrow(metrics[before_k], metrics[after_k])
            label.setText(text)
            label.setStyleSheet(f"{borderless_style()} color: {color};")

    def _clear_fit_panel(self) -> None:
        for lbl in (
            self.lbl_slope, self.lbl_intercept, self.lbl_r2,
            self.lbl_nsamples, self.lbl_range,
            self.lbl_test_n, self.lbl_mean_bias, self.lbl_mae,
            self.lbl_rmse, self.lbl_max_err,
        ):
            lbl.setText("—")
            lbl.setStyleSheet(borderless_style())

    def _on_save(self) -> None:
        if self._current_model is None:
            self._toast("Fit a model first.", is_warning=True)
            return

        w = MessageBox(
            "Save and Activate?",
            "Saving this model will deactivate any existing calibration\n"
            "for this material / wavelength / mode and make this one\n"
            "the active correction at measurement time.\n\nProceed?",
            self,
        )
        w.yesButton.setText("Save & Activate")
        w.cancelButton.setText("Cancel")
        if not w.exec():
            return

        new_id = self.calibration_service.save(self._current_model, set_active=True)
        if new_id <= 0:
            self._toast("Saving the calibration failed. See log.", is_error=True)
            return

        self.calibration_activated.emit(new_id)
        self._toast(
            f"Saved calibration (ID {new_id}) and activated it.",
            is_error=False,
        )
        self._refresh_filter_options()

    # ==================================================================
    # Helpers
    # ==================================================================

    def refresh_data(self) -> None:
        """Public hook used by the controller when measurements change."""
        self._refresh_filter_options()

    def _toast(
        self, message: str, *,
        is_error: bool = False, is_warning: bool = False, duration: int = 4000,
    ) -> None:
        if is_error:
            InfoBar.error(title="Error", content=message, duration=duration,
                          parent=self, position=InfoBarPosition.TOP)
        elif is_warning:
            InfoBar.warning(title="Notice", content=message, duration=duration,
                            parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.success(title="OK", content=message, duration=duration,
                            parent=self, position=InfoBarPosition.TOP)