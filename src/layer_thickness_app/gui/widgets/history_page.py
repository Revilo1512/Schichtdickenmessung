from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore    import Qt, QDate, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QInputDialog, QMenu,
    QDialog, QFormLayout, QDialogButtonBox, QScrollArea,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, DatePicker,
    PrimaryPushButton, PushButton, TableWidget, ToolButton,
    FluentIcon, SubtitleLabel, StrongBodyLabel,
    InfoBar, InfoBarPosition, MessageBox,
)

from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.gui.theme import muted_label_style, FlowLayout

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detail popup
# ---------------------------------------------------------------------------

# Field key -> human label. Order is kept stable for predictable layout.
_DETAIL_FIELDS: list[tuple[str, str]] = [
    ("Date",               "Date"),
    ("Name",               "Name"),
    ("Layer",              "Layer (nm)"),
    ("ThicknessCorrected", "Corrected (nm)"),
    ("ReferenceThickness", "Reference (nm)"),
    ("Wavelength",         "Wavelength (µm)"),
    ("Mode",               "Mode"),
    ("FrameCountSample",   "Frames (sample)"),
    ("FrameCountRef",      "Frames (reference)"),
    ("MeanGrayRef",        "Mean gray (ref)"),
    ("MeanGraySample",     "Mean gray (sample)"),
    ("StdGrayRef",         "Std gray (ref)"),
    ("StdGraySample",      "Std gray (sample)"),
    ("Shelf",              "Shelf"),
    ("Book",               "Book"),
    ("Page",               "Page"),
    ("SessionTag",         "Session tag"),
    ("Probe",              "Probe"),
    ("RunIndex",           "Run index"),
    ("RefImage",           "Reference image"),
    ("MatImage",           "Sample image"),
    ("Note",               "Note"),
]


def _format_detail_value(key: str, value: Any) -> str:
    """Stringify a measurement field for the detail popup."""
    if value is None or value == "":
        return "—"
    if key in ("Layer", "ThicknessCorrected") and isinstance(value, (int, float)):
        return f"{float(value):.4f} nm"
    if key == "ReferenceThickness" and isinstance(value, (int, float)):
        return f"{float(value):g} nm"
    if key == "Wavelength" and isinstance(value, (int, float)):
        return f"{float(value):.3f} µm"
    if key in ("MeanGrayRef", "MeanGraySample",
               "StdGrayRef", "StdGraySample") and isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    if key in ("FrameCountRef", "FrameCountSample", "RunIndex") and isinstance(value, (int, float)):
        return str(int(value))
    if key == "Date" and isinstance(value, str):
        return value[:19]
    return str(value)


class MeasurementDetailsDialog(QDialog):
    """Read-only popup that shows every field of a measurement."""

    def __init__(self, record: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Measurement Details")
        self.setMinimumWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        outer.addWidget(SubtitleLabel("Measurement Details"))

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        host = QWidget()
        form = QFormLayout(host)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        for key, label in _DETAIL_FIELDS:
            text = _format_detail_value(key, record.get(key))
            value_lbl = BodyLabel(text)
            value_lbl.setWordWrap(True)
            value_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            form.addRow(StrongBodyLabel(f"{label}:"), value_lbl)

        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        # The default Close button triggers ``rejected``; map both signals
        # so either Esc or the button closes the dialog.
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(
            self.accept
        )
        outer.addWidget(buttons)


class HistoryPage(QWidget):
    """
    Browser for the measurement history with filtering, pagination,
    inline editing and bulk deletion.
    """

    data_changed = pyqtSignal()

    # Visible columns kept deliberately small. Less-relevant fields
    # (id, frames, shelf, full notes) live in the row-detail popup.
    _COL_DATE      = 0
    _COL_NAME      = 1
    _COL_LAYER     = 2
    _COL_CORRECTED = 3
    _COL_REF       = 4
    _COL_WAVE      = 5
    _COL_MODE      = 6
    _COL_BOOK      = 7
    _COL_PAGE      = 8
    _COL_SESSION   = 9

    # Map table columns to DB columns.
    _COL_DB_KEY: dict[int, str | None] = {
        _COL_DATE:      "Date",
        _COL_NAME:      "Name",
        _COL_LAYER:     "Layer",
        _COL_CORRECTED: "ThicknessCorrected",
        _COL_REF:       "ReferenceThickness",
        _COL_WAVE:      "Wavelength",
        _COL_MODE:      "Mode",
        _COL_BOOK:      "Book",
        _COL_PAGE:      "Page",
        _COL_SESSION:   "SessionTag",
    }

    _COL_LABELS = [
        "Date",       "Name",       "Layer (nm)",
        "Corr. (nm)", "Ref (nm)",   "λ (µm)",
        "Mode",       "Book",       "Page",      "Session",
    ]

    # The DB id is hidden but stored as UserRole data on the Date item.
    _ROW_ID_COL = _COL_DATE
    _ROW_ID_ROLE = Qt.ItemDataRole.UserRole

    # Cells the user can edit via the right-click context menu.
    _EDITABLE_COLS = frozenset({_COL_REF, _COL_SESSION})

    def __init__(self, db_service: DatabaseService, parent: QWidget | None = None):
        super().__init__(parent)
        self.db_service = db_service
        self.setObjectName("HistoryPage")

        self.current_page     = 1
        self.items_per_page   = 20
        self.total_items      = 0
        self.total_pages      = 1

        self._init_widgets()
        self._init_layout()
        self._connect_signals()

        self._load_name_suggestions()
        self._refresh_data()

    # ==================================================================
    # Widget / layout
    # ==================================================================

    def _init_widgets(self):
        self.page_title   = SubtitleLabel("History")

        self.name_filter    = ComboBox(self); self.name_filter.setPlaceholderText("Filter by name...")
        self.start_date_filter = DatePicker(self); self.start_date_filter.setDate(QDate(2024, 1, 1))
        self.end_date_filter   = DatePicker(self); self.end_date_filter.setDate(QDate(2030, 12, 31))

        self.sort_order_combo = ComboBox(self)
        self.sort_order_combo.addItems(["Newest First", "Oldest First"])

        self.filter_button  = PrimaryPushButton("Apply Filters", self)
        self.delete_button  = ToolButton(FluentIcon.DELETE, self)
        self.delete_button.setToolTip("Delete filtered data")
        self.reset_button   = PushButton("Reset", self)
        self.refresh_button = ToolButton(FluentIcon.SYNC, self)
        self.refresh_button.setToolTip("Refresh data (reloads filter suggestions too)")

        self.table = TableWidget(self)
        self.table.setColumnCount(len(self._COL_LABELS))
        self.table.setHorizontalHeaderLabels(self._COL_LABELS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Session column stretches to fill leftover horizontal space so
        # nothing is shortened with "..." anywhere visible.
        header.setSectionResizeMode(self._COL_SESSION, QHeaderView.ResizeMode.Stretch)

        self.table.setColumnWidth(self._COL_DATE,      150)
        self.table.setColumnWidth(self._COL_NAME,      110)
        self.table.setColumnWidth(self._COL_LAYER,     95)
        self.table.setColumnWidth(self._COL_CORRECTED, 95)
        self.table.setColumnWidth(self._COL_REF,       85)
        self.table.setColumnWidth(self._COL_WAVE,      70)
        self.table.setColumnWidth(self._COL_MODE,      70)
        self.table.setColumnWidth(self._COL_BOOK,      80)
        self.table.setColumnWidth(self._COL_PAGE,      80)

        self.prev_button = ToolButton(FluentIcon.LEFT_ARROW,  self)
        self.next_button = ToolButton(FluentIcon.RIGHT_ARROW, self)
        self.page_label  = CaptionLabel("Page 1 of 1", self)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _init_layout(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(15)

        # Page title (matches the Validation page style)
        root.addWidget(self.page_title)

        # Filters wrap to a second row at narrow widths.
        filter_host = QWidget(self)
        flow = FlowLayout(filter_host, margin=0, h_spacing=10, v_spacing=8)
        flow.addWidget(self._make_field("Name:",  self.name_filter))
        flow.addWidget(self._make_field("From:",  self.start_date_filter))
        flow.addWidget(self._make_field("To:",    self.end_date_filter))
        flow.addWidget(self._make_field("Sort:",  self.sort_order_combo))
        flow.addWidget(self.filter_button)
        flow.addWidget(self.reset_button)
        flow.addWidget(self.refresh_button)
        flow.addWidget(self.delete_button)
        root.addWidget(filter_host)

        hint = CaptionLabel(
            "Tip: click a row to view full details. "
            "Right-click for edit / delete.",
            self,
        )
        hint.setStyleSheet(muted_label_style())

        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.prev_button)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next_button)
        nav.addStretch(1)

        root.addWidget(hint)
        root.addWidget(self.table, 1)
        root.addLayout(nav)

    @staticmethod
    def _make_field(label_text: str, widget: QWidget) -> QWidget:
        """Label + control bundled so a flow layout never splits the pair."""
        host = QWidget()
        h = QHBoxLayout(host)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(BodyLabel(label_text))
        h.addWidget(widget)
        return host

    def _connect_signals(self):
        self.filter_button.clicked.connect(self._on_filter_apply)
        self.delete_button.clicked.connect(self._on_delete_filtered)
        self.reset_button.clicked.connect(self._on_filter_reset)
        self.refresh_button.clicked.connect(self._on_full_refresh)
        self.sort_order_combo.currentIndexChanged.connect(self._on_filter_apply)
        self.prev_button.clicked.connect(self._on_prev_page)
        self.next_button.clicked.connect(self._on_next_page)

        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

    # ==================================================================
    # Filter handlers
    # ==================================================================

    def _on_filter_apply(self):
        self.current_page = 1
        self._refresh_data()

    def _on_filter_reset(self):
        self.name_filter.setCurrentIndex(-1)
        self.start_date_filter.setDate(QDate(2024, 1, 1))
        self.end_date_filter.setDate(QDate(2030, 12, 31))
        self.sort_order_combo.setCurrentIndex(0)
        self.current_page = 1
        self._refresh_data()

    def _on_full_refresh(self):
        self._load_name_suggestions()
        self._refresh_data()

    def refresh_data(self) -> None:
        """Public hook used by the controller when measurements change."""
        self._load_name_suggestions()
        self._refresh_data()

    def _on_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._refresh_data()

    def _on_next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._refresh_data()

    # ==================================================================
    # Data loading
    # ==================================================================

    def _load_name_suggestions(self):
        """Repopulate the Name filter combo, preserving current selection."""
        current_name = self.name_filter.currentText()
        names = self.db_service.get_unique_names()
        self.name_filter.blockSignals(True)
        self.name_filter.clear()
        self.name_filter.addItems(names)
        if current_name in names:
            self.name_filter.setCurrentText(current_name)
        else:
            self.name_filter.setCurrentIndex(-1)
        self.name_filter.blockSignals(False)

    def _get_current_filters(self) -> dict[str, Any]:
        name = self.name_filter.currentText() or None
        start = self.start_date_filter.date
        end   = self.end_date_filter.date
        return {
            "name_filter": name,
            "start_date":  start.toString("yyyy-MM-dd") if start.isValid() else None,
            "end_date":    end.toString("yyyy-MM-dd")   if end.isValid()   else None,
        }

    def _refresh_data(self):
        """
        Reloads the current page using the windowed-count paginated read,
        which gives us rows + total in a single round-trip.
        """
        filters  = self._get_current_filters()
        sort_dir = "DESC" if self.sort_order_combo.currentIndex() == 0 else "ASC"

        rows, total = self.db_service.get_measurements(
            **filters,
            page_num  = self.current_page,
            per_page  = self.items_per_page,
            order_by  = "Date",
            order_dir = sort_dir,
        )

        self.total_items = total
        self.total_pages = max(
            1, (self.total_items + self.items_per_page - 1) // self.items_per_page
        )
        self.current_page = min(self.current_page, self.total_pages)

        self._populate_table(rows)

        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.prev_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < self.total_pages)

    def _populate_table(self, measurements: list[dict[str, Any]]):
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(measurements))

            for row_idx, record in enumerate(measurements):
                for col_idx, db_key in self._COL_DB_KEY.items():
                    value = record.get(db_key) if db_key else ""
                    item  = self._build_item(col_idx, db_key, value)
                    if col_idx == self._ROW_ID_COL:
                        # Stash the DB id on the row's date cell — kept
                        # off-screen so users don't see it but recoverable
                        # by every action that needs it.
                        item.setData(self._ROW_ID_ROLE, record.get("id"))
                    self.table.setItem(row_idx, col_idx, item)
        finally:
            self.table.setUpdatesEnabled(True)

    def _build_item(
        self, col_idx: int, db_key: str | None, value: Any,
    ) -> QTableWidgetItem:
        empty_with_dash = (
            "ReferenceThickness", "ThicknessCorrected",
            "SessionTag", "Mode",
        )
        if value is None or value == "":
            text = "—" if db_key in empty_with_dash else ""
        elif db_key == "Layer" and isinstance(value, float):
            text = f"{value:.2f}"
        elif db_key == "ThicknessCorrected" and isinstance(value, (int, float)):
            text = f"{float(value):.2f}"
        elif db_key == "ReferenceThickness" and isinstance(value, (int, float)):
            text = f"{float(value):g}"
        elif db_key == "Wavelength" and isinstance(value, float):
            text = f"{value:.3f}"
        elif db_key == "Date" and isinstance(value, str):
            text = value[:19]
        else:
            text = str(value)

        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Full text on hover so nothing is silently truncated.
        if text and text != "—":
            item.setToolTip(text)
        return item

    # ==================================================================
    # Bulk delete
    # ==================================================================

    def _on_delete_filtered(self):
        filters = self._get_current_filters()
        count   = self.db_service.get_measurements_count(**filters)
        if count == 0:
            self._show_info_bar("No Data", "No items match the filters to delete.",
                                is_error=True)
            return

        msg = (
            f"You are about to permanently delete {count} measurement(s) "
            f"matching the current filters.\n\n"
            f"This also deletes their image files.\nAre you sure?"
        )
        w = MessageBox("Delete Measurements?", msg, self)
        w.yesButton.setText("Delete"); w.cancelButton.setText("Cancel")
        if w.exec():
            self._perform_deletion(filters)

    def _perform_deletion(self, filters: dict[str, Any]):
        try:
            measurements = self.db_service.get_all_filtered_measurements(**filters)
            if not measurements:
                self._show_info_bar("No Data", "No items found to delete.",
                                    is_error=True)
                return

            deleted = 0
            for record in measurements:
                if self.db_service.delete_measurement(record["id"]):
                    deleted += 1

            self._show_info_bar("Success",
                                f"Successfully deleted {deleted} measurement(s).",
                                is_error=False)
            if deleted > 0:
                self.data_changed.emit()

            self._on_filter_reset()
        except Exception as e:
            logger.exception("Error during bulk deletion: %s", e)
            self._show_info_bar("Deletion Error",
                                f"An unexpected error occurred: {e}",
                                is_error=True)

    # ==================================================================
    # Inline editing
    # ==================================================================

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        # Double-click anywhere in the row opens the full-record popup.
        self._show_details_popup(row)

    def _on_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row, _col = index.row(), index.column()

        menu = QMenu(self.table)
        act_view      = menu.addAction("View Details…")
        menu.addSeparator()
        act_edit_ref  = menu.addAction("Edit Reference Thickness…")
        act_edit_ses  = menu.addAction("Edit Session Tag…")
        act_edit_note = menu.addAction("Edit Note…")
        menu.addSeparator()
        act_delete    = menu.addAction("Delete this row…")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action is act_view:      self._show_details_popup(row)
        if action is act_edit_ref:  self._edit_cell(row, self._COL_REF)
        if action is act_edit_ses:  self._edit_cell(row, self._COL_SESSION)
        if action is act_edit_note: self._edit_cell(row, "_NOTE")
        if action is act_delete:    self._delete_single(row)

    def _row_id(self, row: int) -> int | None:
        item = self.table.item(row, self._ROW_ID_COL)
        if item is None:
            return None
        val = item.data(self._ROW_ID_ROLE)
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def _edit_cell(self, row: int, col_or_key) -> None:
        """
        Pop the appropriate small dialog and write the new value back.
        ``col_or_key`` is either a visible column index (REF/SESSION) or
        the sentinel ``"_NOTE"`` for the off-table Note field.
        """
        row_id = self._row_id(row)
        if row_id is None:
            return
        record = self.db_service.get_measurement(row_id)
        if record is None:
            self._show_info_bar("Error", "Row not found in database.",
                                is_error=True)
            return

        if col_or_key == self._COL_REF:
            current_value = record.get("ReferenceThickness")
            new_val, ok = QInputDialog.getDouble(
                self, "Edit Reference Thickness",
                "Reference thickness (nm). Enter 0 or leave blank to clear:",
                value    = float(current_value) if current_value is not None else 0.0,
                min      = 0.0,
                max      = 5000.0,
                decimals = 2,
            )
            if not ok:
                return
            new_db_value: Any = None if new_val <= 0 else float(new_val)
            column_to_update  = "ReferenceThickness"
        elif col_or_key == self._COL_SESSION:
            current_value = record.get("SessionTag")
            new_val, ok = QInputDialog.getText(
                self, "Edit Session Tag",
                "Session tag (leave empty to clear):",
                text=str(current_value or ""),
            )
            if not ok:
                return
            new_db_value = new_val.strip() or None
            column_to_update = "SessionTag"
        elif col_or_key == "_NOTE":
            current_value = record.get("Note")
            new_val, ok = QInputDialog.getText(
                self, "Edit Note", "Note:",
                text=str(current_value or ""),
            )
            if not ok:
                return
            new_db_value = new_val or None
            column_to_update = "Note"
        else:
            return

        if self._update_single_field(row_id, column_to_update, new_db_value):
            self._refresh_data()
            self.data_changed.emit()
        else:
            self._show_info_bar("Update failed",
                                "Could not write change to database.",
                                is_error=True)

    def _update_single_field(
        self, row_id: int, column: str, value: Any,
    ) -> bool:
        """
        Direct UPDATE on the measurements table. The column name is
        whitelisted so a plain f-string is safe here.
        """
        allowed = {"ReferenceThickness", "SessionTag", "Note"}
        if column not in allowed:
            logger.error("Rejected update to column %s", column)
            return False
        try:
            self.db_service.cursor.execute(
                f"UPDATE measurements SET {column} = ? WHERE id = ?",
                (value, row_id),
            )
            self.db_service.conn.commit()
            return self.db_service.cursor.rowcount > 0
        except Exception as e:
            logger.exception("Update failed: %s", e)
            return False

    def _delete_single(self, row: int) -> None:
        row_id = self._row_id(row)
        if row_id is None:
            return

        w = MessageBox(
            "Delete this row?",
            f"Permanently delete measurement #{row_id} (and its image files)?",
            self,
        )
        w.yesButton.setText("Delete"); w.cancelButton.setText("Cancel")
        if not w.exec():
            return

        if self.db_service.delete_measurement(row_id):
            self._show_info_bar("Deleted", f"Measurement #{row_id} removed.")
            self._refresh_data()
            self.data_changed.emit()
        else:
            self._show_info_bar("Error", "Could not delete that row.",
                                is_error=True)

    # ==================================================================
    # Detail popup
    # ==================================================================

    def _show_details_popup(self, row: int) -> None:
        row_id = self._row_id(row)
        if row_id is None:
            return
        record = self.db_service.get_measurement(row_id)
        if record is None:
            self._show_info_bar("Error", "Row not found in database.",
                                is_error=True)
            return
        dlg = MeasurementDetailsDialog(record, self)
        dlg.exec()

    # ==================================================================
    # Helpers
    # ==================================================================

    def _show_info_bar(self, title: str, content: str, is_error: bool = False):
        if is_error:
            InfoBar.error(title=title, content=content, duration=5000,
                          parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.success(title=title, content=content, duration=3000,
                            parent=self, position=InfoBarPosition.TOP)