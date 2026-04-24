from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme

logger = logging.getLogger(__name__)


class AppConfig(QObject):
    """
    Application configuration persisted to config.json next to this file.

    In addition to the user-facing theme / language / window-size settings,
    the class also exposes a handful of read-only configuration
    surfaces (wavelength list, default frame count, DB path, plausibility
    defaults). These are kept in one place so that UI code doesn't have
    to import service-internal constants — if any of them need to change
    per deployment, they can be made persisted settings without touching
    each caller.
    """

    theme_changed       = pyqtSignal(Theme)
    language_changed    = pyqtSignal(str)
    window_size_changed = pyqtSignal(str)

    DEFAULT_CONFIG = {
        "theme":       "Auto",
        "language":    "English",
        "window_size": "1100x800",
    }

    # ---- Non-persisted (code-level) configuration surface -----------
    # Wavelengths offered in the measurement / calibration dropdowns.
    # Tuples are (display_label, value_in_um).
    WAVELENGTHS: tuple[tuple[str, float], ...] = (
        ("Red (635 nm)",   0.635),
        ("Green (532 nm)", 0.532),
    )
    # Default number of frames to average per capture.
    FRAME_COUNT_DEFAULT: int   = 30
    # On-disk SQLite path, relative to the working directory.
    DB_PATH:             str   = "data/measurements.db"

    # Plausibility fallback thresholds (applied when no MaterialProfile
    # is available). Profiles always take precedence.
    PLAUSIBILITY_SAT_ERR:  float = 254.0
    PLAUSIBILITY_SAT_WARN: float = 240.0
    PLAUSIBILITY_SIG_ERR:  float = 10.0
    PLAUSIBILITY_SIG_WARN: float = 20.0

    def __init__(self):
        super().__init__()
        # Absolute path: config.json sits next to this config.py file.
        self.config_path = Path(__file__).resolve().parent / "config.json"
        self._config_data: dict = {}
        self.load()

    def _get_theme_enum(self, theme_str: str) -> Theme:
        if theme_str == "Dark":
            return Theme.DARK
        if theme_str == "Light":
            return Theme.LIGHT
        return Theme.AUTO

    def load(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Error creating config directory %s: %s",
                         self.config_path.parent, e)

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config_data = json.load(f)
                # Back-fill missing keys with defaults.
                for key, value in self.DEFAULT_CONFIG.items():
                    self._config_data.setdefault(key, value)
            except json.JSONDecodeError:
                logger.error("Error reading config file %s. Loading defaults.",
                             self.config_path)
                self._config_data = self.DEFAULT_CONFIG.copy()
        else:
            logger.info("No config file found. Creating with defaults at %s",
                        self.config_path)
            self._config_data = self.DEFAULT_CONFIG.copy()

        self.save()

    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
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
        if theme_str in ("Light", "Dark", "Auto"):
            self._config_data["theme"] = theme_str
            self.save()
            self.theme_changed.emit(self.theme_enum)

    # --- Language ---
    @property
    def language(self) -> str:
        return self._config_data.get("language", "English")

    def set_language(self, language_str: str):
        if language_str in ("English", "German"):
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


# Global configuration instance
cfg = AppConfig()