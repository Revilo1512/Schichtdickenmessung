import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication

# Import classes directly from their specific submodule
from qfluentwidgets import SettingCardGroup, ComboBoxSettingCard, Theme, setTheme, FluentIcon
from qfluentwidgets.common.config import QConfig, OptionsValidator, OptionsConfigItem

# Create a configuration mapping
class Config(QConfig):
    """ Configuration of application """
    themeMode = OptionsConfigItem(
        "Appearance", "Theme", Theme.AUTO, OptionsValidator([Theme.LIGHT, Theme.DARK, Theme.AUTO]), restart=True)
    language = OptionsConfigItem(
        "Appearance", "Language", "English", OptionsValidator(["English", "German"]), restart=True)

# Create a global config instance
cfg = Config()

class SettingsPage(QWidget):
    """ Page for application settings, including theme and language. """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")

        self.setting_group = SettingCardGroup("Application Settings", self)
        
        # --- FIX: Added the 'texts' parameter with display names for the combo box ---
        self.theme_card = ComboBoxSettingCard(
            cfg.themeMode,
            FluentIcon.BRUSH,
            "Theme",
            "Change the appearance of the application",
            texts=["Light", "Dark", "System"],  # <-- Required list of display texts
            parent=self.setting_group
        )

        # --- FIX: Added the 'texts' parameter with display names for the combo box ---
        self.language_card = ComboBoxSettingCard(
            cfg.language,
            FluentIcon.LANGUAGE,
            "Language",
            "Change the application language (requires restart)",
            texts=["English", "German"],  # <-- Required list of display texts
            parent=self.setting_group
        )

        # --- Layout ---
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 20)
        self.main_layout.addWidget(self.setting_group)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.setting_group.addSettingCard(self.theme_card)
        self.setting_group.addSettingCard(self.language_card)

        # --- Connect Signals ---
        cfg.themeMode.valueChanged.connect(setTheme)

