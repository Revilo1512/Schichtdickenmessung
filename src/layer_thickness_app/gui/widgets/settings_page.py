"""
Application settings page. Theme, language, window size and an
"About" entry that links to the project repository.
"""

from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QDesktopServices

from qfluentwidgets import (
    SettingCardGroup, ComboBoxSettingCard, FluentIcon,
    OptionsConfigItem, PushSettingCard, OptionsValidator,
)

from layer_thickness_app.config.config import AppConfig

GITHUB_URL = "https://github.com/Revilo1512/Schichtdickenmessung"


class SettingsPage(QWidget):
    """Application settings page."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setObjectName("settings_page")

        self.init_settings()
        self.init_layout()

    def init_layout(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 20)

        self.main_layout.addWidget(self.setting_group)
        self.main_layout.addSpacing(10)
        self.main_layout.addWidget(self.window_group)
        self.main_layout.addSpacing(10)
        self.main_layout.addWidget(self.about_group)
        self.main_layout.addStretch(1)

        self.setting_group.addSettingCard(self.theme_card)
        self.setting_group.addSettingCard(self.language_card)
        self.window_group.addSettingCard(self.window_size_card)
        self.about_group.addSettingCard(self.github_card)

        self.theme_config_item.valueChanged.connect(self.on_theme_changed)
        self.lang_config_item.valueChanged.connect(self.on_language_changed)
        self.size_config_item.valueChanged.connect(self.on_window_size_changed)

        self.github_card.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL))
        )

    def init_settings(self):
        self.setting_group = SettingCardGroup("General", self)
        self.window_group  = SettingCardGroup("Window", self)
        self.about_group   = SettingCardGroup("About", self)

        theme_options = ["Light", "Dark", "Auto"]
        self.theme_config_item = OptionsConfigItem(
            "General", "Theme", self.config.theme,
            OptionsValidator(theme_options),
        )

        lang_options = ["English", "German"]
        self.lang_config_item = OptionsConfigItem(
            "General", "Language", self.config.language,
            OptionsValidator(lang_options),
        )

        size_options = ["1100x800", "1280x900", "1600x1000", "Fullscreen"]
        self.size_config_item = OptionsConfigItem(
            "Window", "WindowSize", self.config.window_size,
            OptionsValidator(size_options),
        )

        self.theme_card = ComboBoxSettingCard(
            self.theme_config_item,
            FluentIcon.BRUSH,
            "Theme",
            "Change the appearance of the application",
            texts=theme_options,
            parent=self.setting_group,
        )

        self.language_card = ComboBoxSettingCard(
            self.lang_config_item,
            FluentIcon.LANGUAGE,
            "Language",
            "Change the application language",
            texts=lang_options,
            parent=self.setting_group,
        )
        self.language_card.setEnabled(False)

        self.window_size_card = ComboBoxSettingCard(
            self.size_config_item,
            FluentIcon.APPLICATION,
            "Window Size",
            "Set the application window size",
            texts=size_options,
            parent=self.window_group,
        )

        self.github_card = PushSettingCard(
            "Visit on GitHub",
            FluentIcon.GITHUB,
            "Repository",
            "View the source code, report issues, or contribute.",
            self.about_group,
        )

    def on_theme_changed(self, theme_str: str):
        self.config.set_theme(theme_str)

    def on_language_changed(self, lang_str: str):
        self.config.set_language(lang_str)

    def on_window_size_changed(self, size_str: str):
        self.config.set_window_size(size_str)