import sys
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QDesktopServices

from qfluentwidgets import (SettingCardGroup, ComboBoxSettingCard, setTheme, FluentIcon,
                            OptionsConfigItem, PushSettingCard, OptionsValidator)

from layer_thickness_app.config.config import AppConfig

class SettingsPage(QWidget):
    """ Page for application settings """

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("settings_page")

        # --- General Settings Group ---
        self.setting_group = SettingCardGroup("General", self)

        # --- FIX 1: Create ConfigItems ---
        
        # Define theme options and create the ConfigItem
        theme_options = ["Light", "Dark", "Auto"]
        theme_validator = OptionsValidator(theme_options)
        self.theme_config_item = OptionsConfigItem(
            "General", "Theme", self.config.theme, theme_validator
        )

        # Define language options and create the ConfigItem
        lang_options = ["English", "German"]
        lang_validator = OptionsValidator(lang_options)
        self.lang_config_item = OptionsConfigItem(
            "General", "Language", self.config.language , lang_validator
        )

        # Theme Card
        self.theme_card = ComboBoxSettingCard(
            self.theme_config_item,  # <-- Pass the config item, not None
            FluentIcon.BRUSH,
            "Theme",
            "Change the appearance of the application",
            texts=theme_options,    # texts argument is for display names
            parent=self.setting_group
        )
        # self.theme_card.setValue() is no longer needed; the ConfigItem handles it.

        # Language Card
        self.language_card = ComboBoxSettingCard(
            self.lang_config_item, # <-- Pass the config item, not None
            FluentIcon.LANGUAGE,
            "Language",
            "Change the application language (requires restart)",
            texts=lang_options,
            parent=self.setting_group
        )

        # --- Window Settings Group ---
        self.window_group = SettingCardGroup("Window", self)

        # --- FIX 2: Repeat for other cards ---
        
        # Define window size options and create the ConfigItem
        size_options = ["1100x800", "1280x900", "1600x1000", "Fullscreen"]
        size_validator = OptionsValidator(size_options)
        self.size_config_item = OptionsConfigItem(
            "Window", "WindowSize", self.config.window_size, size_validator
        )

        # Window Size Card
        self.window_size_card = ComboBoxSettingCard(
            self.size_config_item, # <-- Pass the config item, not None
            FluentIcon.APPLICATION,
            "Window Size",
            "Set the application window size",
            texts=size_options,
            parent=self.window_group
        )

        # --- About Group ---
        self.about_group = SettingCardGroup("About", self)
        
        self.github_card = PushSettingCard(
            "Visit on GitHub",
            FluentIcon.GITHUB,
            "Repository",
            "View the source code, report issues, or contribute.",
            self.about_group
        )
        self.github_card.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/google/gemini-examples")))


        # --- Layout ---
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 20)
        self.main_layout.addWidget(self.setting_group)
        self.main_layout.addWidget(self.window_group)
        self.main_layout.addWidget(self.about_group)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Add cards to groups
        self.setting_group.addSettingCard(self.theme_card)
        self.setting_group.addSettingCard(self.language_card)
        self.window_group.addSettingCard(self.window_size_card)
        self.about_group.addSettingCard(self.github_card)
        
        # --- FIX 3: Connect signals to the ConfigItem ---
        self.theme_config_item.valueChanged.connect(self.on_theme_changed)
        self.lang_config_item.valueChanged.connect(self.on_language_changed)
        self.size_config_item.valueChanged.connect(self.on_window_size_changed)

        # Connect config signals
        self.config.theme_changed.connect(setTheme) 
        
    def on_theme_changed(self, theme_str: str):
        """Called when the user changes the theme in the combobox."""
        self.config.set_theme(theme_str)
        
    def on_language_changed(self, lang_str: str):
        """Called when the user changes the language."""
        self.config.set_language(lang_str)
        
    def on_window_size_changed(self, size_str: str):
        """Called when the user changes the window size."""
        self.config.set_window_size(size_str)