from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme

logger = logging.getLogger(__name__)


class AppConfig(QObject):
    """
    Persistent application configuration backed by ``config.json``.

    User-facing settings (theme, language, window size) are persisted.
    Code-level surfaces (wavelengths, default frame count, DB path,
    plausibility fallback thresholds) are exposed here so the UI never
    has to reach into service internals for shared constants.
    """

    theme_changed       = pyqtSignal(Theme)
    language_changed    = pyqtSignal(str)
    window_size_changed = pyqtSignal(str)
    # Emitted with the new exposure in ms (float). Signals subscribers
    # that the value has been written to disk.
    camera_exposure_changed = pyqtSignal(float)

    DEFAULT_CONFIG = {
        "theme":              "Auto",
        "language":           "English",
        "window_size":        "1100x800",
        # None = "use whatever default the camera firmware ships with".
        # A float overrides on every connect.
        "camera_exposure_ms": None,
    }

    # ---- Code-level (non-persisted) configuration -------------------
    WAVELENGTHS: tuple[tuple[str, float], ...] = (
        ("Red (635 nm)",   0.635),
        ("Green (532 nm)", 0.532),
    )
    FRAME_COUNT_DEFAULT: int = 30
    DB_PATH:             str = "data/measurements.db"

    # Plausibility thresholds. The transmission setup produces a small
    # bright spot in an otherwise dark frame, so saturation and signal
    # strength are derived from the spot, not the global gray mean.
    #
    # Saturation is detected by the fraction of pixels at or above 254;
    # a tiny clipped patch in the centre is enough to invalidate the
    # measurement, so the error threshold is conservative.
    PLAUSIBILITY_SAT_FRAC_ERR:  float = 0.0050
    PLAUSIBILITY_SAT_FRAC_WARN: float = 0.0010

    # Signal strength is the mean over the top 0.5 % of pixels (the
    # laser spot). For thick layers most of the frame is dark, but the
    # spot itself must remain well above the sensor noise floor.
    PLAUSIBILITY_HOTSPOT_ERR:  float = 25.0
    PLAUSIBILITY_HOTSPOT_WARN: float = 50.0

    def __init__(self):
        super().__init__()
        self.config_path = Path(__file__).resolve().parent / "config.json"
        self._config_data: dict = {}
        self.load()

    # ------------------------------------------------------------------

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

    # --- Theme -------------------------------------------------------

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

    # --- Language ----------------------------------------------------

    @property
    def language(self) -> str:
        return self._config_data.get("language", "English")

    def set_language(self, language_str: str):
        if language_str in ("English", "German"):
            self._config_data["language"] = language_str
            self.save()
            self.language_changed.emit(language_str)

    # --- Window Size -------------------------------------------------

    @property
    def window_size(self) -> str:
        return self._config_data.get("window_size", "1100x800")

    def set_window_size(self, size_str: str):
        if "x" in size_str or size_str == "Fullscreen":
            self._config_data["window_size"] = size_str
            self.save()
            self.window_size_changed.emit(size_str)

    # --- Camera exposure ---------------------------------------------

    @property
    def camera_exposure_ms(self) -> float | None:
        """
        Persisted camera exposure time in milliseconds, or None if no
        override has been set (camera default applies).
        """
        v = self._config_data.get("camera_exposure_ms")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid camera_exposure_ms in config (%r); ignoring.", v,
            )
            return None

    def set_camera_exposure_ms(self, value_ms: float | None) -> None:
        """Persist a camera exposure override. Pass None to clear it."""
        if value_ms is None:
            self._config_data["camera_exposure_ms"] = None
        else:
            self._config_data["camera_exposure_ms"] = float(value_ms)
        self.save()
        # Emit only for non-null updates so listeners don't have to
        # special-case "clear".
        if value_ms is not None:
            self.camera_exposure_changed.emit(float(value_ms))


cfg = AppConfig()