import os
import sys
from pathlib import Path

GLOBAL_CONFIG_FILENAME = "config.toml"
APPLICATION_NAME = "context-forge"


def global_config_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APPLICATION_NAME

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / APPLICATION_NAME

        return Path.home() / "AppData" / "Roaming" / APPLICATION_NAME

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / APPLICATION_NAME

    return Path.home() / ".config" / APPLICATION_NAME


def global_config_path() -> Path:
    return global_config_directory() / GLOBAL_CONFIG_FILENAME
