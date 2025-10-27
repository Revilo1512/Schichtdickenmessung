import os

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog
from qfluentwidgets import (
    BodyLabel, SubtitleLabel, ComboBox, DatePicker, PrimaryPushButton,
    PushButton, InfoBar, InfoBarPosition
)
from typing import Dict, Any, Optional

from layer_thickness_app.services.database_service import DatabaseService
from layer_thickness_app.services.import_service import ImportService
from layer_thickness_app.services.export_service import ExportService

class CSVPage(QWidget):
    """
    A page for importing and exporting measurement data with filters.
    """
    def __init__(self, 
                 db_service: DatabaseService, 
                 import_service: ImportService, 
                 export_service: ExportService, 
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db_service = db_service
        self.import_service = import_service
        self.export_service = export_service
        
        self.setObjectName("csv_page")

        self._init_widgets()
        self._init_layout()
        self._connect_signals()
        self._load_filter_suggestions()

    def _init_widgets(self):
        """Initialize all UI widgets."""
        self.filter_title = SubtitleLabel("Export Filters")
        
        # --- Filter Widgets ---
        self.name_filter = ComboBox(self)
        self.name_filter.setPlaceholderText("Filter by name...")
        self.name_filter.setEnabled(True)

        self.start_date_filter = DatePicker(self)
        self.start_date_filter.setDate(QDate())

        self.end_date_filter = DatePicker(self)
        self.end_date_filter.setDate(QDate())

        self.shelf_filter = ComboBox(self)
        self.shelf_filter.setPlaceholderText("Filter by shelf...")
        
        self.book_filter = ComboBox(self)
        self.book_filter.setPlaceholderText("Filter by book...")
        
        self.page_filter = ComboBox(self)
        self.page_filter.setPlaceholderText("Filter by page...")

        # --- Action Widgets ---
        self.count_label = BodyLabel("Items to export: 0")
        
        self.update_count_button = PushButton("Update Count")
        self.reset_filters_button = PushButton("Reset Filters")

        self.export_button = PrimaryPushButton("Export to ZIP", self)
        self.export_button.setEnabled(False) # Disabled until count > 0

        self.import_button = PushButton("Import from ZIP", self)

    def _init_layout(self):
        """Set up the layout."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 20)
        self.main_layout.setSpacing(15)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(self.filter_title)

        # Filter grid layout
        filter_layout = QGridLayout()
        filter_layout.setSpacing(10)
        
        # Row 0
        filter_layout.addWidget(BodyLabel("Name:"), 0, 0)
        filter_layout.addWidget(self.name_filter, 0, 1)
        filter_layout.addWidget(BodyLabel("From:"), 0, 2)
        filter_layout.addWidget(self.start_date_filter, 0, 3)
        filter_layout.addWidget(BodyLabel("To:"), 0, 4)
        filter_layout.addWidget(self.end_date_filter, 0, 5)
        
        # Row 1
        filter_layout.addWidget(BodyLabel("Shelf:"), 1, 0)
        filter_layout.addWidget(self.shelf_filter, 1, 1)
        filter_layout.addWidget(BodyLabel("Book:"), 1, 2)
        filter_layout.addWidget(self.book_filter, 1, 3)
        filter_layout.addWidget(BodyLabel("Page:"), 1, 4)
        filter_layout.addWidget(self.page_filter, 1, 5)
        
        filter_layout.setColumnStretch(1, 2)
        filter_layout.setColumnStretch(3, 2)
        filter_layout.setColumnStretch(5, 2)

        self.main_layout.addLayout(filter_layout)
        self.main_layout.addSpacing(10)

        # --- Count and Action Layout ---
        count_layout = QHBoxLayout()
        count_layout.addWidget(self.count_label, 1, Qt.AlignmentFlag.AlignLeft)
        count_layout.addStretch(1)
        count_layout.addWidget(self.reset_filters_button)
        count_layout.addWidget(self.update_count_button)
        self.main_layout.addLayout(count_layout)

        self.main_layout.addSpacing(20)

        # --- Ex-/Import Button Layout ---
        ex_import_layout = QHBoxLayout()
        ex_import_layout.addWidget(self.import_button)
        ex_import_layout.addStretch(1)
        ex_import_layout.addWidget(self.export_button)
        self.main_layout.addLayout(ex_import_layout)

    def _connect_signals(self):
        """Connect widget signals to slots."""
        self.update_count_button.clicked.connect(self.on_update_count)
        self.reset_filters_button.clicked.connect(self.on_reset_filters)
        self.export_button.clicked.connect(self.on_export)
        self.import_button.clicked.connect(self.on_import)

    def _load_filter_suggestions(self):
        """Populates all filter comboboxes from the database."""
        # Names
        names = self.db_service.get_unique_names()
        self.name_filter.clear()
        self.name_filter.addItems(names)
        self.name_filter.setCurrentIndex(-1)
        self.name_filter.setText("")

        # Shelves
        shelves = self.db_service.get_unique_shelves()
        self.shelf_filter.clear()
        self.shelf_filter.addItems(shelves)
        self.shelf_filter.setCurrentIndex(-1)
        
        # Books
        books = self.db_service.get_unique_books()
        self.book_filter.clear()
        self.book_filter.addItems(books)
        self.book_filter.setCurrentIndex(-1)
        
        # Pages
        pages = self.db_service.get_unique_pages()
        self.page_filter.clear()
        self.page_filter.addItems(pages)
        self.page_filter.setCurrentIndex(-1)

    def _get_current_filters(self) -> Dict[str, Any]:
        """Helper to get all filter values as a dictionary."""
        name = self.name_filter.text()
        start_date_q = self.start_date_filter.date
        end_date_q = self.end_date_filter.date
        shelf = self.shelf_filter.currentText()
        book = self.book_filter.currentText()
        page = self.page_filter.currentText()

        return {
            "name_filter": name if name else None,
            "start_date": start_date_q.toString("yyyy-MM-dd") if start_date_q.isValid() else None,
            "end_date": end_date_q.toString("yyyy-MM-dd") if end_date_q.isValid() else None,
            "shelf": shelf if shelf else None,
            "book": book if book else None,
            "page": page if page else None
        }

    def on_update_count(self):
        """Updates the count label based on the current filters."""
        filters = self._get_current_filters()
        count = self.db_service.get_measurements_count(**filters)
        
        self.count_label.setText(f"Items to export: {count}")
        self.export_button.setEnabled(count > 0)
        
        if count == 0:
            self._show_info_bar("No Matches", "No measurements match the current filters.", is_error=True)

    def on_reset_filters(self):
        """Clears all filters and resets the count."""
        self.name_filter.setCurrentIndex(-1)
        self.name_filter.setText("")
        self.start_date_filter.setDate(QDate())
        self.end_date_filter.setDate(QDate())
        self.shelf_filter.setCurrentIndex(-1)
        self.book_filter.setCurrentIndex(-1)
        self.page_filter.setCurrentIndex(-1)
        
        self.count_label.setText("Items to export: 0")
        self.export_button.setEnabled(False)

    def on_export(self):
        """Opens a dialog to choose an export directory and runs the export."""
        # Get export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Folder",
            os.path.expanduser("~") # Start in user's home directory
        )
        
        if not export_dir:
            return # User cancelled

        try:
            filters = self._get_current_filters()
            filepath = self.export_service.export_to_zip(export_dir, **filters)
            
            if filepath:
                self._show_info_bar("Export Successful", f"Data exported to {filepath}", is_error=False)
            else:
                self._show_info_bar("Export Failed", "No data was exported. See console for details.", is_error=True)
        except Exception as e:
            print(f"Error during export: {e}")
            self._show_info_bar("Export Error", f"An unexpected error occurred: {e}", is_error=True)

    def on_import(self):
        """Opens a dialog to choose a CSV file and runs the import."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select ZIP File to Import",
            os.path.expanduser("~"),
            "ZIP Files (*.zip)"
        )
        
        if not filepath:
            return # User cancelled

        try:
            success_count, fail_count = self.import_service.import_from_zip(filepath)
            
            if success_count > 0 and fail_count == 0:
                self._show_info_bar(
                    "Import Successful",
                    f"Successfully imported {success_count} rows.",
                    is_error=False
                )
            elif success_count > 0 and fail_count > 0:
                self._show_info_bar(
                    "Import Partially Successful",
                    f"Imported {success_count} rows. {fail_count} rows failed.",
                    is_error=True # Show as warning/error
                )
            elif success_count == 0 and fail_count > 0:
                self._show_info_bar(
                    "Import Failed",
                    f"All {fail_count} rows failed. Check console for details.",
                    is_error=True
                )
            else: # 0, 0
                self._show_info_bar(
                    "Import Warning",
                    "No data was imported. The file might be empty, invalid or missing headers.",
                    is_error=True
                )
            
            # Refresh filter suggestions
            self._load_filter_suggestions()
            
        except Exception as e:
            print(f"Error during import: {e}")
            self._show_info_bar("Import Error", f"An unexpected error occurred: {e}", is_error=True)

    def _show_info_bar(self, title: str, content: str, is_error: bool = False):
        """Shows a success or error InfoBar message."""
        if is_error:
            InfoBar.error(
                title=title,
                content=content,
                duration=5000,
                parent=self,
                position=InfoBarPosition.TOP
            )
        else:
            InfoBar.success(
                title=title,
                content=content,
                duration=3000,
                parent=self,
                position=InfoBarPosition.TOP
            )