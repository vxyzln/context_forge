import os
import sys
from pathlib import Path

GLOBAL_CONFIG_FILENAME = "config.toml"
APPLICATION_NAME = "context-forge"


def global_config_directory() -> Path:
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data and app_data.strip():
            return Path(app_data.strip()) / APPLICATION_NAME

        return Path.home() / "AppData" / "Roaming" / APPLICATION_NAME

    return Path.home() / ".config" / APPLICATION_NAME


def global_config_path() -> Path:
    return global_config_directory() / GLOBAL_CONFIG_FILENAME
