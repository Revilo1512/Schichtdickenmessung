import sys
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidgetItem, QAbstractItemView, QHeaderView
from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, DatePicker, PrimaryPushButton,
    PushButton, TableWidget, ToolButton, FluentIcon, SubtitleLabel
)
from typing import List, Dict, Any
from layer_thickness_app.services.database_service import DatabaseService

class HistoryPage(QWidget):
    """
    A page to display, filter, and paginate measurement history.
    """
    def __init__(self, db_service: DatabaseService, parent=None):
        super().__init__(parent)
        self.db_service = db_service
        self.setObjectName("HistoryPage")

        # Pagination state
        self.current_page = 1
        self.items_per_page = 20  # Show 20 items per page
        self.total_items = 0
        self.total_pages = 1

        # Define table headers (must match DB columns)
        self.headers = ["id", "Date", "Name", "Layer", "RefImage", "MatImage", "Shelf", "Book", "Page"]
        self.header_labels = ["ID", "Date", "Name", "Layer", "Ref Image", "Mat Image", "Shelf", "Book", "Page"]

        # --- UI Initialization ---
        self._init_widgets()
        self._init_layout()
        self._connect_signals()

        # --- Initial Data Load ---
        self._load_name_suggestions()
        #self._refresh_data()

    def _init_widgets(self):
        """Initialize all UI widgets."""
        self.filter_title = SubtitleLabel("Filters")

        # Name Filter (with suggestions)
        self.name_filter = ComboBox(self)
        self.name_filter.setPlaceholderText("Filter by name...")
        self.name_filter.setEnabled(True)

        # Date Filters
        self.start_date_filter = DatePicker(self)
        #self.start_date_filter.setDefault("Start date")
        #self.start_date_filter.clear() # Start empty

        self.end_date_filter = DatePicker(self)
        #self.end_date_filter.setDefault("End date")
        #self.end_date_filter.clear() # Start empty

        # Filter Buttons
        self.filter_button = PrimaryPushButton("Apply Filters", self)
        self.reset_button = PushButton("Reset", self)

        # Data Table
        self.table = TableWidget(self)
        self.table.setColumnCount(len(self.header_labels))
        self.table.setHorizontalHeaderLabels(self.header_labels)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # Read-only
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) # Allow ID resize
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)


        # Pagination Controls
        #self.prev_button = ToolButton(FluentIcon.CHEVRON_D, self)
        self.next_button = ToolButton(FluentIcon.CHEVRON_RIGHT, self)
        self.page_label = CaptionLabel("Page 1 of 1", self)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _init_layout(self):
        """Set up the layout."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Filter layout
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.filter_title)
        filter_layout.addSpacing(10)
        filter_layout.addWidget(self.name_filter, 1)
        filter_layout.addSpacing(10)
        filter_layout.addWidget(BodyLabel("From:", self))
        filter_layout.addWidget(self.start_date_filter)
        filter_layout.addSpacing(5)
        filter_layout.addWidget(BodyLabel("To:", self))
        filter_layout.addWidget(self.end_date_filter)
        filter_layout.addSpacing(10)
        filter_layout.addWidget(self.filter_button)
        filter_layout.addWidget(self.reset_button)
        filter_layout.addStretch(2)

        # Pagination layout
        nav_layout = QHBoxLayout()
        nav_layout.addStretch(1)
        #nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.next_button)
        nav_layout.addStretch(1)

        # Add to main layout
        self.main_layout.addLayout(filter_layout)
        self.main_layout.addWidget(self.table, 1) # Table gets all the stretch
        self.main_layout.addLayout(nav_layout)

    def _connect_signals(self):
        """Connect widget signals to slots."""
        self.filter_button.clicked.connect(self._on_filter_apply)
        self.reset_button.clicked.connect(self._on_filter_reset)
        #self.prev_button.clicked.connect(self._on_prev_page)
        self.next_button.clicked.connect(self._on_next_page)
        
        # Optional: Allow pressing Enter in name filter to apply
        #self.name_filter.lineEdit().returnPressed.connect(self._on_filter_apply)

    def _load_name_suggestions(self):
        """Fetches unique names from DB and populates the ComboBox."""
        names = self.db_service.get_unique_names()
        self.name_filter.clear()
        self.name_filter.addItems(names)
        self.name_filter.setCurrentIndex(-1) # Clear selection

    def _on_filter_apply(self):
        """Resets to page 1 and refreshes data based on filters."""
        self.current_page = 1
        self._refresh_data()

    def _on_filter_reset(self):
        """Clears all filters, resets to page 1, and refreshes."""
        self.name_filter.setCurrentIndex(-1)
        #self.name_filter.clearEditText()
        #self.start_date_filter.clear()
        #self.end_date_filter.clear()
        self.current_page = 1
        self._refresh_data()

    def _on_prev_page(self):
        """Goes to the previous page."""
        if self.current_page > 1:
            self.current_page -= 1
            self._refresh_data()

    def _on_next_page(self):
        """Goes to the next page."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._refresh_data()

    def _refresh_data(self):
        """
        Fetches the correct data from the DB based on filters and
        current page, then updates the table and pagination controls.
        """
        # 1. Get filter values
        name = self.name_filter.text()
        start_date_q = self.start_date_filter.date()
        #start_date_str = start_date_q.toString("yyyy-MM-dd") if start_date_q.isValid() else None
        
        end_date_q = self.end_date_filter.date()
        #end_date_str = end_date_q.toString("yyyy-MM-dd") if end_date_q.isValid() else None

        # 2. Update total count and pages
        self.total_items = self.db_service.get_measurements_count(
            #name, start_date_str, end_date_str
        )
        self.total_pages = max(1, (self.total_items + self.items_per_page - 1) // self.items_per_page)
        
        # Adjust current page if it's now out of bounds (e.g., after filtering)
        self.current_page = min(self.current_page, self.total_pages)

        # 3. Fetch data for the current page
        measurements = self.db_service.get_measurements(
            #name, start_date_str, end_date_str, self.current_page, self.items_per_page
        )

        # 4. Populate the table
        self._populate_table(measurements)

        # 5. Update pagination controls
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        #self.prev_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < self.total_pages)
        
    def _populate_table(self, measurements: List[Dict[str, Any]]):
        """Clears and refills the table with new data."""
        self.table.setRowCount(0) # Clear table
        self.table.setRowCount(len(measurements))

        for row_idx, record in enumerate(measurements):
            for col_idx, key in enumerate(self.headers):
                value = record.get(key, "")
                
                # Format floating point numbers nicely
                if key == 'Layer' and isinstance(value, float):
                    item = QTableWidgetItem(f"{value:.4f}")
                else:
                    item = QTableWidgetItem(str(value))
                
                # Center-align numbers
                if key in ('id', 'Layer'):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                self.table.setItem(row_idx, col_idx, item)