import json
import logging
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme

logger = logging.getLogger(__name__)

class AppConfig(QObject):
    """
    Manages the application's configuration, saved in a JSON file.
    Uses signals to notify the application of changes.
    """
    
    theme_changed = pyqtSignal(Theme)
    language_changed = pyqtSignal(str)
    window_size_changed = pyqtSignal(str)

    DEFAULT_CONFIG = {
        "theme": "Auto",
        "language": "English",
        "window_size": "1100x800"
    }

    def __init__(self):
        super().__init__()
        # Absoluter Pfad: Speichert die config.json immer im selben Ordner wie diese config.py
        self.config_path = Path(__file__).resolve().parent / "config.json"
        self._config_data = {}
        self.load()

    def _get_theme_enum(self, theme_str: str) -> Theme:
        if theme_str == "Dark":
            return Theme.DARK
        elif theme_str == "Light":
            return Theme.LIGHT
        return Theme.AUTO

    def load(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Error creating config directory %s: %s", self.config_path.parent, e)
            
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config_data = json.load(f)
                
                # Fehlende Schlüssel mit Standardwerten auffüllen
                for key, value in self.DEFAULT_CONFIG.items():
                    self._config_data.setdefault(key, value)
            except json.JSONDecodeError:
                logger.error("Error reading config file %s. Loading defaults.", self.config_path)
                self._config_data = self.DEFAULT_CONFIG.copy()
        else:
            logger.info("No config file found. Creating with defaults at %s", self.config_path)
            self._config_data = self.DEFAULT_CONFIG.copy()
        
        self.save()

    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=4)
        except OSError as e:
            logger.error("Error saving config file: %s", e)

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
        if "x" in size_str or size_str == "Fullscreen":
            self._config_data["window_size"] = size_str
            self.save()
            self.window_size_changed.emit(size_str)

# Globales Konfigurationsobjekt erstellen
cfg = AppConfig()