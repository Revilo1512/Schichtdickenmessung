from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from qfluentwidgets import SettingCardGroup, ComboBoxSettingCard, setTheme, FluentIcon

from layer_thickness_app.config.config import cfg

class SettingsPage(QWidget):
    """ Page for application settings """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")

        self.setting_group = SettingCardGroup("Application Settings", self)
        
        self.theme_card = ComboBoxSettingCard(
            cfg.themeMode,
            FluentIcon.BRUSH,
            "Theme",
            "Change the appearance of the application",
            texts=["Light", "Dark", "System"],
            parent=self.setting_group
        )

        self.language_card = ComboBoxSettingCard(
            cfg.language,
            FluentIcon.LANGUAGE,
            "Language",
            "Change the application language",
            texts=["English", "German"],
            parent=self.setting_group
        )

        # layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(40, 20, 40, 20)
        self.main_layout.addWidget(self.setting_group)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.setting_group.addSettingCard(self.theme_card)
        self.setting_group.addSettingCard(self.language_card)

        # connect signals
        cfg.themeMode.valueChanged.connect(setTheme)
        
        

