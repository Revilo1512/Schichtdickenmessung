import yaml
import pathlib
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

