"""
CSV import / export page. Provides filter controls for the export
selection and a one-click ZIP import that re-populates the database.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QFrame, QFormLayout,
)
from qfluentwidgets import (
    BodyLabel, SubtitleLabel, ComboBox, DatePicker,
    PrimaryPushButton, PushButton, InfoBar, InfoBarPosition,
)

from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.import_service   import ImportService
from layer_thickness_app.services.export_service   import ExportService
from layer_thickness_app.gui.theme import card_style, borderless_style

logger = logging.getLogger(__name__)

_EXPORT_CARD_OBJECT_NAME = "csv_export_card"
_IMPORT_CARD_OBJECT_NAME = "csv_import_card"


class CSVPage(QWidget):
    """Import and export page with filter selection."""

    data_changed = pyqtSignal()

    def __init__(
        self,
        db_service:     DatabaseService,
        import_service: ImportService,
        export_service: ExportService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.db_service     = db_service
        self.import_service = import_service
        self.export_service = export_service

        # Suppress info bars during the initial population.
        self._is_loading = True

        self.setObjectName("csv_page")

        self._init_widgets()
        self._init_layout()
        self._connect_signals()
        self._load_filter_suggestions()

        self.on_update_count()
        self._is_loading = False

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _init_widgets(self):
        self.filter_title = SubtitleLabel("Export Filters")
        self.import_title = SubtitleLabel("Import")

        self.name_filter = ComboBox(self)
        self.name_filter.setPlaceholderText("Filter by name...")

        self.start_date_filter = DatePicker(self)
        self.start_date_filter.setDate(QDate(2024, 1, 1))

        self.end_date_filter = DatePicker(self)
        self.end_date_filter.setDate(QDate(2030, 12, 31))

        self.shelf_filter = ComboBox(self)
        self.shelf_filter.setPlaceholderText("Filter by shelf...")

        self.book_filter = ComboBox(self)
        self.book_filter.setPlaceholderText("Filter by book...")

        self.page_filter = ComboBox(self)
        self.page_filter.setPlaceholderText("Filter by page...")

        self.count_label = BodyLabel("Items to export: 0")

        self.reset_filters_button = PushButton("Reset Filters")

        self.export_button = PrimaryPushButton("Export to ZIP", self)
        self.export_button.setEnabled(False)

        self.import_button = PrimaryPushButton("Import from ZIP", self)

    def _init_layout(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 20)
        self.main_layout.addStretch(1)

        card_container_layout = QHBoxLayout()
        card_container_layout.setSpacing(20)
        card_container_layout.addStretch(1)

        # Export card
        self.export_card = QFrame(self)
        self.export_card.setObjectName(_EXPORT_CARD_OBJECT_NAME)
        self.export_card.setStyleSheet(card_style(_EXPORT_CARD_OBJECT_NAME))
        self.export_card.setFixedWidth(400)

        export_layout = QVBoxLayout(self.export_card)
        export_layout.setContentsMargins(25, 25, 25, 25)
        export_layout.setSpacing(15)

        self.filter_title.setStyleSheet(borderless_style())
        export_layout.addWidget(self.filter_title)

        filter_form_layout = QFormLayout()
        filter_form_layout.setSpacing(10)

        def make_label(text: str) -> BodyLabel:
            lbl = BodyLabel(text)
            lbl.setStyleSheet(borderless_style())
            return lbl

        filter_form_layout.addRow(make_label("Name:"),  self.name_filter)
        filter_form_layout.addRow(make_label("From:"),  self.start_date_filter)
        filter_form_layout.addRow(make_label("To:"),    self.end_date_filter)
        filter_form_layout.addRow(make_label("Shelf:"), self.shelf_filter)
        filter_form_layout.addRow(make_label("Book:"),  self.book_filter)
        filter_form_layout.addRow(make_label("Page:"),  self.page_filter)

        export_layout.addLayout(filter_form_layout)

        self.count_label.setStyleSheet(f"{borderless_style()} font-weight: bold;")
        count_layout = QHBoxLayout()
        count_layout.addWidget(self.count_label, 1, Qt.AlignmentFlag.AlignLeft)
        count_layout.addStretch(1)
        count_layout.addWidget(self.reset_filters_button)

        export_layout.addLayout(count_layout)
        export_layout.addStretch(1)
        export_layout.addWidget(self.export_button)

        card_container_layout.addWidget(self.export_card)

        # Import card
        self.import_card = QFrame(self)
        self.import_card.setObjectName(_IMPORT_CARD_OBJECT_NAME)
        self.import_card.setStyleSheet(card_style(_IMPORT_CARD_OBJECT_NAME))
        self.import_card.setFixedWidth(400)

        import_layout = QVBoxLayout(self.import_card)
        import_layout.setContentsMargins(25, 25, 25, 25)

        self.import_title.setStyleSheet(borderless_style())
        self.import_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        import_layout.addWidget(self.import_title)
        import_layout.addStretch(1)
        import_layout.addWidget(self.import_button, 0, Qt.AlignmentFlag.AlignHCenter)
        import_layout.addStretch(1)

        card_container_layout.addWidget(self.import_card)
        card_container_layout.addStretch(1)

        self.main_layout.addLayout(card_container_layout)
        self.main_layout.addStretch(1)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.reset_filters_button.clicked.connect(self.on_reset_filters)
        self.export_button.clicked.connect(self.on_export)
        self.import_button.clicked.connect(self.on_import)

        self.name_filter.currentTextChanged.connect(self.on_update_count)
        self.start_date_filter.dateChanged.connect(self.on_update_count)
        self.end_date_filter.dateChanged.connect(self.on_update_count)
        self.shelf_filter.currentTextChanged.connect(self.on_update_count)
        self.book_filter.currentTextChanged.connect(self.on_update_count)
        self.page_filter.currentTextChanged.connect(self.on_update_count)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_filter_suggestions(self):
        """Repopulates the filter combos from the database."""
        for combo in (self.name_filter, self.shelf_filter,
                      self.book_filter, self.page_filter):
            combo.blockSignals(True)

        self.name_filter.clear()
        self.name_filter.addItems(self.db_service.get_unique_names())
        self.name_filter.setCurrentIndex(-1)

        self.shelf_filter.clear()
        self.shelf_filter.addItems(self.db_service.get_unique_shelves())
        self.shelf_filter.setCurrentIndex(-1)

        self.book_filter.clear()
        self.book_filter.addItems(self.db_service.get_unique_books())
        self.book_filter.setCurrentIndex(-1)

        self.page_filter.clear()
        self.page_filter.addItems(self.db_service.get_unique_pages())
        self.page_filter.setCurrentIndex(-1)

        for combo in (self.name_filter, self.shelf_filter,
                      self.book_filter, self.page_filter):
            combo.blockSignals(False)

    def _get_current_filters(self) -> dict[str, Any]:
        name  = self.name_filter.currentText()
        start = self.start_date_filter.date
        end   = self.end_date_filter.date
        shelf = self.shelf_filter.currentText()
        book  = self.book_filter.currentText()
        page  = self.page_filter.currentText()

        return {
            "name_filter": name if name else None,
            "start_date":  start.toString("yyyy-MM-dd") if start.isValid() else None,
            "end_date":    end.toString("yyyy-MM-dd")   if end.isValid()   else None,
            "shelf":       shelf if shelf else None,
            "book":        book  if book  else None,
            "page":        page  if page  else None,
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def on_update_count(self):
        filters = self._get_current_filters()
        count = self.db_service.get_measurements_count(**filters)

        self.count_label.setText(f"Items to export: {count}")
        self.export_button.setEnabled(count > 0)

        if count == 0 and not self._is_loading:
            self._show_info_bar(
                "No Matches",
                "No measurements match the current filters.",
                is_error=True,
            )

    def on_reset_filters(self):
        for w in (
            self.name_filter, self.start_date_filter, self.end_date_filter,
            self.shelf_filter, self.book_filter, self.page_filter,
        ):
            w.blockSignals(True)

        self.name_filter.setCurrentIndex(-1)
        self.start_date_filter.setDate(QDate(2024, 1, 1))
        self.end_date_filter.setDate(QDate(2030, 12, 31))
        self.shelf_filter.setCurrentIndex(-1)
        self.book_filter.setCurrentIndex(-1)
        self.page_filter.setCurrentIndex(-1)

        for w in (
            self.name_filter, self.start_date_filter, self.end_date_filter,
            self.shelf_filter, self.book_filter, self.page_filter,
        ):
            w.blockSignals(False)

        self.on_update_count()

    def on_export(self):
        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Folder", str(Path.home()),
        )
        if not export_dir:
            return

        try:
            filters = self._get_current_filters()
            filepath = self.export_service.export_to_zip(export_dir, **filters)

            if filepath:
                self._show_info_bar(
                    "Export Successful",
                    f"Data exported to {filepath}",
                    is_error=False,
                )
            else:
                self._show_info_bar(
                    "Export Failed",
                    "No data was exported. See console for details.",
                    is_error=True,
                )
        except Exception as e:
            logger.exception("Error during export: %s", e)
            self._show_info_bar(
                "Export Error", f"An unexpected error occurred: {e}", is_error=True,
            )

    def on_import(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select ZIP File to Import", str(Path.home()),
            "ZIP Files (*.zip)",
        )
        if not filepath:
            return

        try:
            success_count, fail_count = self.import_service.import_from_zip(filepath)

            if success_count > 0 and fail_count == 0:
                self._show_info_bar(
                    "Import Successful",
                    f"Successfully imported {success_count} rows.",
                    is_error=False,
                )
            elif success_count > 0 and fail_count > 0:
                self._show_info_bar(
                    "Import Partially Successful",
                    f"Imported {success_count} rows. {fail_count} rows failed.",
                    is_error=True,
                )
            elif success_count == 0 and fail_count > 0:
                self._show_info_bar(
                    "Import Failed",
                    f"All {fail_count} rows failed. Check log for details.",
                    is_error=True,
                )
            else:
                self._show_info_bar(
                    "Import Warning",
                    "No data was imported. The file might be empty, invalid or missing headers.",
                    is_error=True,
                )

            self._load_filter_suggestions()
            self.on_update_count()

            if success_count > 0:
                self.data_changed.emit()

        except Exception as e:
            logger.exception("Error during import: %s", e)
            self._show_info_bar(
                "Import Error", f"An unexpected error occurred: {e}", is_error=True,
            )

    def _show_info_bar(self, title: str, content: str, is_error: bool = False):
        if is_error:
            InfoBar.error(
                title=title, content=content, duration=5000,
                parent=self, position=InfoBarPosition.TOP,
            )
        else:
            InfoBar.success(
                title=title, content=content, duration=3000,
                parent=self, position=InfoBarPosition.TOP,
            )