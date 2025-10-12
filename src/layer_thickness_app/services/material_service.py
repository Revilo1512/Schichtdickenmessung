import yaml
import pathlib
import re
import refractiveindex2 as ri
from typing import Dict, Any

class MaterialService:
    """
    Handles loading and parsing the material catalog from the refractiveindex.info database.
    """
    def __init__(self):
        """
        Initializes the service by locating and parsing the material catalog file.
        Raises FileNotFoundError if the catalog cannot be located.
        """
        try:
            self.material_data = self._load_and_parse_catalog()
        except FileNotFoundError as e:
            # Propagate the error to be handled by the application controller
            raise FileNotFoundError(f"Failed to initialize MaterialService: {e}")

    def get_material_data(self) -> Dict[str, Any]:
        """
        Returns the parsed material data structure.

        Returns:
            A dictionary containing the structured catalog data.
        """
        return self.material_data

    def _find_catalog_path(self) -> pathlib.Path:
        """
        Locates the path to the 'catalog-nk.yml' file within the library.
        
        Raises:
            FileNotFoundError: If any part of the expected directory structure is not found.

        Returns:
            The resolved Path object for the catalog file.
        """
        library_path = pathlib.Path(ri.__file__).resolve().parent
        top_level_database_path = library_path / "database"
        if not top_level_database_path.is_dir():
            raise FileNotFoundError("The top-level 'database' directory was not found in the library path.")
        
        # The database folder has a unique hash name, so we find the first subdirectory
        hash_folder = next((p for p in top_level_database_path.iterdir() if p.is_dir()), None)
        if not hash_folder:
            raise FileNotFoundError("Could not find the hash-named database subfolder.")
            
        catalog_file_path = hash_folder / "database" / "catalog-nk.yml"
        if not catalog_file_path.is_file():
            raise FileNotFoundError(f"Catalog file not found at expected path: {catalog_file_path}")
            
        return catalog_file_path

    def _parse_catalog_yml(self, file_path: str) -> Dict[str, Any]:
        """
        Correctly parses the nested catalog-nk.yml file, including DIVIDER entries.
        Dividers are added with special keys like '__DIVIDER_1', '__DIVIDER_2', etc.
        """
        data_structure = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                catalog_data = yaml.safe_load(f)

            divider_count = 0
            for top_level_item in catalog_data:
                if 'DIVIDER' in top_level_item:
                    key = f"__DIVIDER_{divider_count}__"
                    data_structure[key] = {'name': top_level_item['DIVIDER'], 'books': {}}
                    divider_count += 1
                elif 'SHELF' in top_level_item:
                    shelf_key = top_level_item['SHELF']
                    shelf_name = top_level_item.get('name', shelf_key)
                    data_structure[shelf_key] = {'name': shelf_name, 'books': {}}

                    for book_item in top_level_item.get('content', []):
                        if 'DIVIDER' in book_item:
                            key = f"__DIVIDER_{divider_count}__"
                            data_structure[shelf_key]['books'][key] = {'name': book_item['DIVIDER'], 'pages': {}}
                            divider_count += 1
                        elif 'BOOK' in book_item:
                            book_key = book_item['BOOK']
                            book_name = book_item.get('name', book_key)
                            current_book_entry = {'name': book_name, 'pages': {}}
                            data_structure[shelf_key]['books'][book_key] = current_book_entry

                            for page_item in book_item.get('content', []):
                                if 'DIVIDER' in page_item:
                                    key = f"__DIVIDER_{divider_count}__"
                                    current_book_entry['pages'][key] = {'name': page_item['DIVIDER']}
                                    divider_count += 1
                                elif 'PAGE' in page_item:
                                    page_key = page_item['PAGE']
                                    page_name = page_item.get('name', page_key)
                                    current_book_entry['pages'][page_key] = {'name': page_name}
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            return {}
        return data_structure

    def _load_and_parse_catalog(self) -> Dict[str, Any]:
        """Finds, loads, and parses the catalog file."""
        catalog_path = self._find_catalog_path()
        return self._parse_catalog_yml(str(catalog_path))







import sys
import yaml
import pathlib
import re
import refractiveindex2 as ri  # <<< CORRECTED IMPORT
from PyQt6.QtWidgets import QApplication, QWidget, QComboBox, QVBoxLayout, QLabel, QMessageBox
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont
from PyQt6.QtCore import Qt

def parse_catalog_yml(file_path: str) -> dict:
    """
    Correctly parses the nested catalog-nk.yml file, including DIVIDER entries.
    Dividers are added with special keys like '__DIVIDER_1', '__DIVIDER_2', etc.
    """
    data_structure = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            catalog_data = yaml.safe_load(f)

        divider_count = 0
        for top_level_item in catalog_data:
            if 'DIVIDER' in top_level_item:
                key = f"__DIVIDER_{divider_count}__"
                data_structure[key] = {'name': top_level_item['DIVIDER'], 'books': {}}
                divider_count += 1
            elif 'SHELF' in top_level_item:
                shelf_key = top_level_item['SHELF']
                shelf_name = top_level_item.get('name', shelf_key)
                data_structure[shelf_key] = {'name': shelf_name, 'books': {}}

                for book_item in top_level_item.get('content', []):
                    if 'DIVIDER' in book_item:
                        key = f"__DIVIDER_{divider_count}__"
                        data_structure[shelf_key]['books'][key] = {'name': book_item['DIVIDER'], 'pages': {}}
                        divider_count += 1
                    elif 'BOOK' in book_item:
                        book_key = book_item['BOOK']
                        book_name = book_item.get('name', book_key)
                        current_book_entry = {'name': book_name, 'pages': {}}
                        data_structure[shelf_key]['books'][book_key] = current_book_entry

                        for page_item in book_item.get('content', []):
                            if 'DIVIDER' in page_item:
                                key = f"__DIVIDER_{divider_count}__"
                                current_book_entry['pages'][key] = {'name': page_item['DIVIDER']}
                                divider_count += 1
                            elif 'PAGE' in page_item:
                                page_key = page_item['PAGE']
                                page_name = page_item.get('name', page_key)
                                current_book_entry['pages'][page_key] = {'name': page_name}
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return {}
    return data_structure

class MaterialSelector(QWidget):
    def __init__(self, data: dict):
        super().__init__()
        self.data = data
        self.setWindowTitle("Material Selector")
        self.setMinimumWidth(500)

        # --- Create Widgets ---
        self.shelf_combo = QComboBox()
        self.book_combo = QComboBox()
        self.page_combo = QComboBox()
        self.result_label = QLabel("Selected Path: ")
        
        # We need a model to disable items
        self.shelf_model = QStandardItemModel()
        self.book_model = QStandardItemModel()
        self.page_model = QStandardItemModel()
        
        self.shelf_combo.setModel(self.shelf_model)
        self.book_combo.setModel(self.book_model)
        self.page_combo.setModel(self.page_model)
        
        # --- CHANGE 1: Create a font for dividers ---
        self.divider_font = QFont()
        self.divider_font.setItalic(True)

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Shelf:"))
        layout.addWidget(self.shelf_combo)
        layout.addWidget(QLabel("Book (Material):"))
        layout.addWidget(self.book_combo)
        layout.addWidget(QLabel("Page (Dataset):"))
        layout.addWidget(self.page_combo)
        layout.addSpacing(20)
        layout.addWidget(self.result_label)

        # Connect Signals
        self.shelf_combo.currentIndexChanged.connect(self._on_shelf_changed)
        self.book_combo.currentIndexChanged.connect(self._on_book_changed)
        self.page_combo.currentIndexChanged.connect(self._update_selection_display)

        # Initial Population
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
                # --- CHANGE 2: Make dividers more pronounced ---
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
        # If no item is available, set to -1 (no selection)
        combo.setCurrentIndex(-1)

    def _populate_shelves(self):
        self.shelf_combo.blockSignals(True)
        self._populate_combo(self.shelf_combo, self.data)
        self.shelf_combo.blockSignals(False)
        
        # --- CHANGE 3: Select first VALID item, not just index 0 ---
        self._select_first_available(self.shelf_combo)

    def _on_shelf_changed(self, index=-1):
        self.book_combo.blockSignals(True)
        
        shelf_key = self.shelf_combo.currentData()
        books = {}
        if shelf_key:
            books = self.data.get(shelf_key, {}).get('books', {})
        
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

    def _update_selection_display(self, index=-1):
        shelf = self.shelf_combo.currentData()
        book = self.book_combo.currentData()
        page = self.page_combo.currentData()

        if shelf and book and page and not str(book).startswith('__DIVIDER'):
            final_path = f"{shelf}/{book}/{page}"
            self.result_label.setText(f"Selected Path: <b>{final_path}</b>")
        else:
            self.result_label.setText("Selected Path: ")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    material_data = None
    try:
        library_path = pathlib.Path(ri.__file__).resolve().parent
        top_level_database_path = library_path / "database"
        if not top_level_database_path.is_dir():
            raise FileNotFoundError("The top-level 'database' directory was not found.")
        
        hash_folder = next((p for p in top_level_database_path.iterdir() if p.is_dir()), None)
        if not hash_folder:
            raise FileNotFoundError("Could not find the hash-named database subfolder.")
            
        catalog_file_path = hash_folder / "database" / "catalog-nk.yml"
        if not catalog_file_path.is_file():
            raise FileNotFoundError(f"Catalog file not found at expected path: {catalog_file_path}")
            
        material_data = parse_catalog_yml(str(catalog_file_path))

    except (ImportError, FileNotFoundError, AttributeError) as e:
        QMessageBox.critical(None, "Error", f"Could not load material database.\n\n{e}")
        sys.exit(1)

    if not material_data:
        QMessageBox.critical(None, "Error", "Failed to parse material data. Check the catalog file.")
        sys.exit(1)

    selector_widget = MaterialSelector(material_data)
    selector_widget.show()
    sys.exit(app.exec())