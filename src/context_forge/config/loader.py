import tomllib
from pathlib import Path
from typing import Any

from context_forge.config.global_config import global_config_path

PROJECT_CONFIG_FILENAME = ".contextforge.toml"


class ConfigurationLoadError(ValueError):
    """Raised when project configuration cannot be loaded."""


def project_config_path(project_root: Path) -> Path:
    return project_root / PROJECT_CONFIG_FILENAME


def load_project_config(project_root: Path) -> dict[str, Any]:
    config_path = project_config_path(project_root)

    if not config_path.exists():
        return {}

    if not config_path.is_file():
        raise ConfigurationLoadError(
            f"Project configuration path is not a file: {config_path}"
        )

    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationLoadError(
            f"Invalid project configuration: {config_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise ConfigurationLoadError(
            f"Could not read project configuration: {config_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigurationLoadError(
            f"Project configuration must contain a TOML table: {config_path}"
        )

    return data


def load_global_config() -> dict[str, Any]:
    config_path = global_config_path()

    if not config_path.exists():
        return {}

    if not config_path.is_file():
        raise ConfigurationLoadError(
            f"Global configuration path is not a file: {config_path}"
        )

    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationLoadError(
            f"Invalid global configuration: {config_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise ConfigurationLoadError(
            f"Could not read global configuration: {config_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigurationLoadError(
            f"Global configuration must contain a TOML table: {config_path}"
        )

    return data
