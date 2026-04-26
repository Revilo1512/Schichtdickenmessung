"""
Material catalog loader. Locates and parses the refractiveindex.info
``catalog-nk.yml`` shipped with the ``refractiveindex2`` package and
exposes it as a nested dict consumed by the MaterialSelector.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
import refractiveindex2 as ri

logger = logging.getLogger(__name__)


class MaterialService:
    """Loads and parses the refractiveindex.info material catalog."""

    def __init__(self):
        try:
            self.material_data: dict[str, Any] = self._load_and_parse_catalog()
            logger.info("Material catalog loaded successfully.")
        except FileNotFoundError as e:
            logger.error("Failed to initialize MaterialService: %s", e)
            raise

    def get_material_data(self) -> dict[str, Any]:
        return self.material_data

    # ------------------------------------------------------------------
    # Catalog discovery
    # ------------------------------------------------------------------

    def _find_catalog_path(self) -> Path:
        """
        Locate ``catalog-nk.yml`` inside the refractiveindex2 package.
        Raises FileNotFoundError if any expected directory is missing.
        """
        library_path        = Path(ri.__file__).resolve().parent
        top_level_db_path   = library_path / "database"

        if not top_level_db_path.is_dir():
            raise FileNotFoundError(
                "The top-level 'database' directory was not found in "
                f"the library path ({top_level_db_path})."
            )

        hash_folder = next(
            (p for p in top_level_db_path.iterdir() if p.is_dir()),
            None,
        )
        if hash_folder is None:
            raise FileNotFoundError(
                f"Could not find the hash-named database subfolder under "
                f"{top_level_db_path}."
            )

        catalog_file_path = hash_folder / "database" / "catalog-nk.yml"
        if not catalog_file_path.is_file():
            raise FileNotFoundError(
                f"Catalog file not found at expected path: {catalog_file_path}"
            )

        return catalog_file_path

    # ------------------------------------------------------------------
    # YAML parsing
    # ------------------------------------------------------------------

    def _parse_catalog_yml(self, file_path: Path) -> dict[str, Any]:
        """
        Parse the nested catalog-nk.yml into a dict suitable for the
        cascading shelf/book/page combo boxes. DIVIDER entries are kept
        as un-selectable separators with synthetic keys.
        """
        data_structure: dict[str, Any] = {}
        try:
            with file_path.open("r", encoding="utf-8") as f:
                catalog_data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            logger.error("Error reading/parsing catalog file %s: %s", file_path, e)
            return {}

        if not catalog_data:
            return {}

        divider_count = 0
        for top_level_item in catalog_data:
            if "DIVIDER" in top_level_item:
                key = f"__DIVIDER_{divider_count}__"
                data_structure[key] = {"name": top_level_item["DIVIDER"], "books": {}}
                divider_count += 1
            elif "SHELF" in top_level_item:
                shelf_key  = top_level_item["SHELF"]
                shelf_name = top_level_item.get("name", shelf_key)
                data_structure[shelf_key] = {"name": shelf_name, "books": {}}

                for book_item in top_level_item.get("content", []):
                    if "DIVIDER" in book_item:
                        key = f"__DIVIDER_{divider_count}__"
                        data_structure[shelf_key]["books"][key] = {
                            "name": book_item["DIVIDER"], "pages": {},
                        }
                        divider_count += 1
                    elif "BOOK" in book_item:
                        book_key  = book_item["BOOK"]
                        book_name = book_item.get("name", book_key)
                        current_book_entry = {"name": book_name, "pages": {}}
                        data_structure[shelf_key]["books"][book_key] = current_book_entry

                        for page_item in book_item.get("content", []):
                            if "DIVIDER" in page_item:
                                key = f"__DIVIDER_{divider_count}__"
                                current_book_entry["pages"][key] = {
                                    "name": page_item["DIVIDER"],
                                }
                                divider_count += 1
                            elif "PAGE" in page_item:
                                page_key  = page_item["PAGE"]
                                page_name = page_item.get("name", page_key)
                                current_book_entry["pages"][page_key] = {"name": page_name}

        return data_structure

    def _load_and_parse_catalog(self) -> dict[str, Any]:
        catalog_path = self._find_catalog_path()
        return self._parse_catalog_yml(catalog_path)