from qfluentwidgets import Theme
from qfluentwidgets.common.config import QConfig, OptionsValidator, OptionsConfigItem

class Config(QConfig):
    """ Application's Config """
    themeMode = OptionsConfigItem("Appearance", "Theme", Theme.AUTO, OptionsValidator([Theme.LIGHT, Theme.DARK, Theme.AUTO]), restart=True)
    language = OptionsConfigItem("Appearance", "Language", "English", OptionsValidator(["English", "German"]), restart=True)


cfg = Config()