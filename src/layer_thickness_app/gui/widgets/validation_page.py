"""
Validation page -- runs MSA Type 1 on a repeated-measurement series and
compares raw vs. corrected thickness output. After a successful run the
study state is kept so the user can dump a timestamped ZIP report.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore    import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame,
    QDoubleSpinBox, QFileDialog,
)
from qfluentwidgets import (
    BodyLabel, SubtitleLabel, StrongBodyLabel, CaptionLabel,
    PushButton, PrimaryPushButton, ComboBox,
    InfoBar, InfoBarPosition, FluentIcon,
)

from layer_thickness_app.services.database_service    import DatabaseService
from layer_thickness_app.services.calibration_service import (
    CalibrationService, CalibrationModel,
)
from layer_thickness_app.services.msa_service         import MSAService, MSAReport
from layer_thickness_app.services.report_service      import ReportService
from layer_thickness_app.gui.theme import (
    card_style, borderless_style, status_label_style, FlowLayout,
    COLOR_SUCCESS, COLOR_WARN, COLOR_ERROR,
)

logger = logging.getLogger(__name__)

_PANEL_OBJECT_NAME = "validation_report_panel"


class ValidationPage(QWidget):
    """MSA Type 1 validation / before-after comparison."""

    def __init__(
        self,
        db_service:          DatabaseService,
        calibration_service: CalibrationService,
        msa_service:         MSAService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("validationPage")

        self.db_service          = db_service
        self.calibration_service = calibration_service
        self.msa_service         = msa_service
        self.report_service      = ReportService()

        self._rows:           list[dict[str, Any]]          = []
        self._models:         list[CalibrationModel | None] = []
        self._last_raw:       MSAReport | None              = None
        self._last_corrected: MSAReport | None              = None
        self._last_model:     CalibrationModel | None       = None
        self._last_material:  str                           = ""

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

        root.addWidget(SubtitleLabel("Validation -- MSA Type 1 (raw vs. corrected)"))

        # Filter bar (FlowLayout wraps to a second row at narrow widths)
        self.book_combo      = ComboBox(self); self.book_combo.setPlaceholderText("Book")
        self.page_combo      = ComboBox(self); self.page_combo.setPlaceholderText("Page")
        self.wave_combo      = ComboBox(self)
        self.wave_combo.addItem("Red (635 nm)", None,   0.635)
        self.wave_combo.addItem("Green (532 nm)", None, 0.532)
        self.mode_combo      = ComboBox(self); self.mode_combo.addItems(["multi", "single"])
        self.session_combo   = ComboBox(self); self.session_combo.setPlaceholderText("Any session")
        self.reference_combo = ComboBox(self); self.reference_combo.setPlaceholderText("Reference (nm)")

        self.load_button = PushButton("Load Measurements", self)
        self.load_button.setIcon(FluentIcon.SYNC)

        filter_host = QWidget(self)
        flow = FlowLayout(filter_host, margin=0, h_spacing=10, v_spacing=8)
        for label, widget in (
            ("Book:",       self.book_combo),
            ("Page:",       self.page_combo),
            ("Wavelength:", self.wave_combo),
            ("Mode:",       self.mode_combo),
            ("Session:",    self.session_combo),
            ("Reference:",  self.reference_combo),
        ):
            flow.addWidget(self._make_field(label, widget))
        flow.addWidget(self.load_button)
        root.addWidget(filter_host)

        # Model + tolerance + run row (also wraps on narrow windows)
        self.model_combo = ComboBox(self)
        self.model_combo.setPlaceholderText("Calibration model...")
        self.model_combo.setMinimumWidth(280)

        self.tolerance_spin = QDoubleSpinBox(self)
        self.tolerance_spin.setRange(0.1, 10_000.0)
        self.tolerance_spin.setDecimals(2)
        self.tolerance_spin.setSingleStep(5.0)
        self.tolerance_spin.setValue(60.0)
        self.tolerance_spin.setSuffix(" nm")
        self.tolerance_spin.setToolTip(
            "Total tolerance band Tol used by the MSA Type 1 study."
        )

        self.rows_loaded_label = CaptionLabel("Rows loaded: 0", self)

        self.run_button    = PrimaryPushButton("Run MSA Type 1", self)
        self.export_button = PushButton("Export Report…", self)
        self.export_button.setIcon(FluentIcon.DOWNLOAD)
        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)

        config_host = QWidget(self)
        config_flow = FlowLayout(config_host, margin=0, h_spacing=10, v_spacing=8)
        config_flow.addWidget(self._make_field("Model:", self.model_combo))
        config_flow.addWidget(self._make_field("Tolerance (Tol):", self.tolerance_spin))
        config_flow.addWidget(self.rows_loaded_label)
        config_flow.addWidget(self.export_button)
        config_flow.addWidget(self.run_button)
        root.addWidget(config_host)

        # Report panels
        report_row = QHBoxLayout()
        report_row.setSpacing(20)

        self.raw_panel       = self._build_report_panel("Raw (uncorrected)")
        self.corrected_panel = self._build_report_panel("Corrected (regression)")

        report_row.addWidget(self.raw_panel,       1)
        report_row.addWidget(self.corrected_panel, 1)
        root.addLayout(report_row, 1)

        # Verdict banner
        self.verdict_label = SubtitleLabel("—")
        self.verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.verdict_label)

    @staticmethod
    def _make_field(label_text: str, widget: QWidget) -> QWidget:
        """
        Bundle a small caption + control into one widget so a flow layout
        can keep them together when wrapping.
        """
        host = QWidget()
        h = QHBoxLayout(host)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(BodyLabel(label_text))
        h.addWidget(widget)
        return host

    def _build_report_panel(self, title: str) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName(_PANEL_OBJECT_NAME)
        frame.setStyleSheet(card_style(_PANEL_OBJECT_NAME))
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 15, 20, 15)
        outer.setSpacing(10)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_lbl = SubtitleLabel(title)
        outer.addWidget(title_lbl)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        labels: dict[str, BodyLabel] = {
            "n":      BodyLabel("—"),
            "mean":   BodyLabel("—"),
            "std":    BodyLabel("—"),
            "bias":   BodyLabel("—"),
            "cg":     BodyLabel("—"),
            "cgk":    BodyLabel("—"),
            "status": BodyLabel("—"),
        }

        form.addRow(StrongBodyLabel("n:"),         labels["n"])
        form.addRow(StrongBodyLabel("Mean (x̄):"), labels["mean"])
        form.addRow(StrongBodyLabel("Std (s):"),   labels["std"])
        form.addRow(StrongBodyLabel("Bias:"),      labels["bias"])
        form.addRow(StrongBodyLabel("Cg:"),        labels["cg"])
        form.addRow(StrongBodyLabel("Cgk:"),       labels["cgk"])
        form.addRow(StrongBodyLabel("Capable?:"),  labels["status"])

        outer.addLayout(form)
        # Push everything to the top so the panel doesn't visually float
        # in the middle when the window is taller than the content.
        outer.addStretch(1)
        frame.labels = labels
        return frame

    # ==================================================================
    # Signal wiring
    # ==================================================================

    def _connect_signals(self) -> None:
        self.book_combo.currentTextChanged.connect(self._on_book_changed)
        self.load_button.clicked.connect(self._on_load)
        self.run_button.clicked.connect(self._on_run)
        self.export_button.clicked.connect(self._on_export)

        for combo in (self.wave_combo, self.mode_combo,
                      self.session_combo, self.reference_combo):
            combo.currentIndexChanged.connect(self._invalidate_run)

    def _invalidate_run(self, *_):
        self.run_button.setEnabled(False)
        self.export_button.setEnabled(False)

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
            self.page_combo.clear(); self.reference_combo.clear(); return

        pages = self.db_service.get_pages_for_book(book)

        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        self.page_combo.addItems(pages)
        self.page_combo.setCurrentIndex(-1)
        self.page_combo.blockSignals(False)

        self.reference_combo.clear()

    def _on_load(self) -> None:
        book = self.book_combo.currentText() or None
        page = self.page_combo.currentText() or None
        if not book or not page:
            self._toast("Select Book and Page first.", is_warning=True); return

        wavelength = self.wave_combo.currentData()
        mode       = self.mode_combo.currentText() or None
        session    = self.session_combo.currentText() or None

        candidates = self.db_service.get_calibration_rows(
            book=book, page=page, session_tag=session,
            wavelength_um=float(wavelength) if wavelength is not None else None,
            mode=mode,
        )
        refs = sorted({r["ReferenceThickness"] for r in candidates
                       if r.get("ReferenceThickness") is not None})

        if self.reference_combo.count() == 0:
            self.reference_combo.blockSignals(True)
            for r in refs:
                self.reference_combo.addItem(f"{r:g} nm", float(r))
            self.reference_combo.blockSignals(False)

        ref_value = self.reference_combo.currentData()
        if ref_value is None:
            self._toast("Select a Reference thickness.", is_warning=True); return

        rows = self.db_service.get_msa_rows(
            book=book, page=page, reference_nm=float(ref_value),
            session_tag=session,
            wavelength_um=float(wavelength) if wavelength is not None else None,
            mode=mode,
            tolerance=0.5,
        )
        rows = [r for r in rows if r.get("Layer") is not None]

        self._rows = rows
        self.rows_loaded_label.setText(f"Rows loaded: {len(rows)}")

        self._populate_model_combo(book=book, page=page,
                                   wavelength=wavelength, mode=mode)

        enough = len(rows) >= self.msa_service.MIN_N
        self.run_button.setEnabled(enough)
        self.export_button.setEnabled(False)
        if not enough:
            self._toast(
                f"Need at least {self.msa_service.MIN_N} measurements for MSA Type 1 "
                f"(got {len(rows)}).",
                is_warning=True,
            )
        self._clear_report_panels()

    def _populate_model_combo(
        self, book: str, page: str,
        wavelength: float | None, mode: str | None,
    ) -> None:
        shelf = self.db_service.get_shelf_for_book_page(book, page) or ""

        active = self.calibration_service.load_active(
            shelf=shelf, book=book, page=page,
            wavelength_um=float(wavelength) if wavelength is not None else 0.0,
            mode=mode or "multi",
        ) if shelf else None

        models = self.calibration_service.list_models(
            shelf=shelf or None, book=book, page=page,
            wavelength_um=float(wavelength) if wavelength is not None else None,
            mode=mode or None,
        )

        self._models = []
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        self.model_combo.addItem("— No correction (raw only) —", None)
        self._models.append(None)

        seen_ids: set[int] = set()
        if active is not None:
            self.model_combo.addItem(f"★ ACTIVE · {active.summary()}", active.id)
            self._models.append(active)
            if active.id is not None:
                seen_ids.add(active.id)

        for m in models:
            if m.id in seen_ids:
                continue
            self.model_combo.addItem(m.summary(), m.id)
            self._models.append(m)

        self.model_combo.setCurrentIndex(1 if self.model_combo.count() > 1 else 0)
        self.model_combo.blockSignals(False)

    # ==================================================================
    # Run MSA + Export
    # ==================================================================

    def _on_run(self) -> None:
        if not self._rows:
            self._toast("Load measurements first.", is_warning=True); return

        reference = self.reference_combo.currentData()
        tolerance = float(self.tolerance_spin.value())
        if reference is None or tolerance <= 0:
            self._toast("Check Reference and Tolerance.", is_warning=True); return

        model_idx = self.model_combo.currentIndex()
        model     = self._models[model_idx] if 0 <= model_idx < len(self._models) else None

        raw_values = [float(r["Layer"]) for r in self._rows]
        material_label = self._material_label("")

        self._last_material = material_label

        if model is None:
            try:
                raw_report = self.msa_service.compute(
                    raw_values, reference_thickness=float(reference),
                    tolerance=tolerance,
                    material=f"{material_label} (raw)",
                )
            except Exception as e:
                self._toast(f"MSA failed: {e}", is_error=True); return

            self._render_report(self.raw_panel, raw_report)
            self._render_empty(self.corrected_panel)
            self._render_verdict(raw_report, None)

            self._last_raw       = raw_report
            self._last_corrected = None
            self._last_model     = None
            self.export_button.setEnabled(True)
            return

        corrected_values = [model.predict(v) for v in raw_values]
        try:
            results = self.msa_service.compare(
                raw=raw_values, corrected=corrected_values,
                reference_thickness=float(reference),
                tolerance=tolerance,
                material=material_label,
            )
        except Exception as e:
            self._toast(f"MSA failed: {e}", is_error=True); return

        self._render_report(self.raw_panel,       results["raw"])
        self._render_report(self.corrected_panel, results["corrected"])
        self._render_verdict(results["raw"], results["corrected"])

        self._last_raw       = results["raw"]
        self._last_corrected = results["corrected"]
        self._last_model     = model
        self.export_button.setEnabled(True)

    def _on_export(self) -> None:
        if self._last_raw is None:
            self._toast("Run a study before exporting.", is_warning=True); return

        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Folder", str(Path.home()),
        )
        if not export_dir:
            return

        reference = float(self.reference_combo.currentData() or 0.0)
        tolerance = float(self.tolerance_spin.value())

        try:
            zip_path = self.report_service.export_msa_study(
                export_dir          = export_dir,
                raw_report          = self._last_raw,
                corrected_report    = self._last_corrected,
                measurements        = self._rows,
                calibration_model   = self._last_model,
                reference_thickness = reference,
                tolerance           = tolerance,
                material_label      = self._last_material or "msa",
            )
        except Exception as e:
            logger.exception("MSA export failed: %s", e)
            self._toast(f"Export failed: {e}", is_error=True); return

        if zip_path:
            self._toast(f"Exported: {zip_path}", duration=5000)
        else:
            self._toast("Export failed -- see log for details.", is_error=True)

    def _material_label(self, suffix: str) -> str:
        parts = [
            self.book_combo.currentText() or "?",
            self.page_combo.currentText() or "?",
            f"{self.wave_combo.currentData()} um",
            self.mode_combo.currentText() or "?",
        ]
        label = " / ".join(parts)
        return f"{label} [{suffix}]" if suffix else label

    # ==================================================================
    # Panel rendering
    # ==================================================================

    @staticmethod
    def _strong_color_style(color: str) -> str:
        return f"{borderless_style()} font-weight: bold; color: {color};"

    def _render_report(self, panel: QFrame, report: MSAReport) -> None:
        labels = panel.labels
        labels["n"].setText(f"{report.n}")
        labels["mean"].setText(f"{report.mean:.4f} nm")
        labels["std"].setText(f"{report.std:.4f} nm")
        labels["bias"].setText(f"{report.bias:.4f} nm")
        labels["cg"].setText(f"{report.cg:.3f}")
        labels["cgk"].setText(f"{report.cgk:.3f}")

        labels["cg"].setStyleSheet(self._strong_color_style(
            COLOR_SUCCESS if report.cg_capable else COLOR_ERROR
        ))
        labels["cgk"].setStyleSheet(self._strong_color_style(
            COLOR_SUCCESS if report.cgk_capable else COLOR_ERROR
        ))
        if report.is_capable:
            labels["status"].setText("CAPABLE ✓")
            labels["status"].setStyleSheet(self._strong_color_style(COLOR_SUCCESS))
        else:
            labels["status"].setText("NOT CAPABLE ✗")
            labels["status"].setStyleSheet(self._strong_color_style(COLOR_ERROR))

    def _render_empty(self, panel: QFrame) -> None:
        for lbl in panel.labels.values():
            lbl.setText("—")
            lbl.setStyleSheet(borderless_style())

    def _clear_report_panels(self) -> None:
        self._render_empty(self.raw_panel)
        self._render_empty(self.corrected_panel)
        self.verdict_label.setText("—")
        self.verdict_label.setStyleSheet("")
        self._last_raw = None
        self._last_corrected = None
        self._last_model = None

    def _render_verdict(self, raw: MSAReport, corrected: MSAReport | None) -> None:
        if corrected is None:
            verdict = ("System is " +
                       ("CAPABLE ✓" if raw.is_capable else "NOT CAPABLE ✗")
                       + f" (Cgk={raw.cgk:.3f})")
            color = COLOR_SUCCESS if raw.is_capable else COLOR_ERROR
        else:
            improvement = corrected.cgk - raw.cgk
            arrow = "↑" if improvement > 0 else ("↓" if improvement < 0 else "=")
            if corrected.is_capable and not raw.is_capable:
                headline = "Calibration made the system CAPABLE ✓";   color = COLOR_SUCCESS
            elif corrected.is_capable and raw.is_capable:
                headline = "System capable before and after.";        color = COLOR_SUCCESS
            elif not corrected.is_capable and raw.is_capable:
                headline = "Warning: correction REDUCED capability."; color = COLOR_WARN
            else:
                headline = "System still NOT capable.";               color = COLOR_ERROR
            verdict = (
                f"{headline}  "
                f"Cgk {raw.cgk:.3f} {arrow} {corrected.cgk:.3f}  "
                f"(Δbias {raw.bias:+.3f} → {corrected.bias:+.3f} nm)"
            )
        self.verdict_label.setText(verdict)
        self.verdict_label.setStyleSheet(self._strong_color_style(color))

    # ==================================================================
    # Public hooks
    # ==================================================================

    def refresh_data(self) -> None:
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