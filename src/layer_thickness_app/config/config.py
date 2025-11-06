import json
import os
from pathlib import Path  # <-- Import Path
from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme

class AppConfig(QObject):
    """
    Manages the application's configuration, saved in a JSON file.
    Uses signals to notify the application of changes.
    """
    
    # Define signals for when settings change
    theme_changed = pyqtSignal(Theme)
    language_changed = pyqtSignal(str)
    window_size_changed = pyqtSignal(str)

    # Define default values
    DEFAULT_CONFIG = {
        "theme": "Auto",
        "language": "English",
        "window_size": "1100x800"
    }

    def __init__(self, config_path: str = "config.json"):
        super().__init__()
        self.config_path = config_path
        self._config_data = {}
        self.load()

    def _get_theme_enum(self, theme_str: str) -> Theme:
        """Converts a theme string to a Theme enum."""
        if theme_str == "Dark":
            return Theme.DARK
        elif theme_str == "Light":
            return Theme.LIGHT
        return Theme.AUTO

    def load(self):
        """Loads the config file or creates it with defaults if it doesn't exist."""
        try:
            config_parent_dir = Path(self.config_path).parent
            config_parent_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Error creating config directory {config_parent_dir}: {e}")
            
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config_data = json.load(f)
                for key, value in self.DEFAULT_CONFIG.items():
                    self._config_data.setdefault(key, value)
            except json.JSONDecodeError:
                print(f"Error reading config file {self.config_path}. Loading defaults.")
                self._config_data = self.DEFAULT_CONFIG.copy()
        else:
            print("No config file found. Creating with defaults.")
            self._config_data = self.DEFAULT_CONFIG.copy()
        
        self.save() # Save to create file or add missing keys

    def save(self):
        """Saves the current configuration to the JSON file."""
        try:
            config_parent_dir = Path(self.config_path).parent
            config_parent_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=4)
        except IOError as e:
            print(f"Error saving config file: {e}")

    # --- Theme ---
    @property
    def theme(self) -> str:
        return self._config_data.get("theme", "Auto")

    @property
    def theme_enum(self) -> Theme:
        return self._get_theme_enum(self.theme)

    def set_theme(self, theme_str: str):
        if theme_str in ["Light", "Dark", "Auto"]:
            self._config_data["theme"] = theme_str
            self.save()
            self.theme_changed.emit(self.theme_enum)

    # --- Language ---
    @property
    def language(self) -> str:
        return self._config_data.get("language", "English")

    def set_language(self, language_str: str):
        if language_str in ["English", "German"]:
            self._config_data["language"] = language_str
            self.save()
            self.language_changed.emit(language_str)

    # --- Window Size ---
    @property
    def window_size(self) -> str:
        return self._config_data.get("window_size", "1100x800")

    def set_window_size(self, size_str: str):
        """size_str should be 'WidthxHeight' or 'Fullscreen'"""
        if "x" in size_str or size_str == "Fullscreen":
            self._config_data["window_size"] = size_str
            self.save()
            self.window_size_changed.emit(size_str)

# Create a single, global instance for the application to use
cfg = AppConfig("src/layer_thickness_app/config/config.json")