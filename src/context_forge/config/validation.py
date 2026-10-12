from typing import Any

from context_forge.config.project import (
    ProjectAnalysisConfiguration,
    ProjectConfiguration,
    ProjectStorageConfiguration,
)


class ConfigurationValidationError(ValueError):
    """Raised when project configuration has an invalid structure or value."""


def validate_project_config(
    data: dict[str, Any],
) -> ProjectConfiguration:
    _validate_top_level(data)

    storage_data = _section(data, "storage")
    analysis_data = _section(data, "analysis")

    return ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path=_optional_string(storage_data, "database_path"),
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=_optional_int(analysis_data, "max_context_units"),
        ),
    )


def _validate_top_level(data: dict[str, Any]) -> None:
    allowed = {"storage", "analysis"}

    unknown = set(data) - allowed

    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationValidationError(f"Unknown configuration section: {names}")


def _section(
    data: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    value = data.get(name)

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ConfigurationValidationError(
            f"Configuration section '{name}' must be a table"
        )

    return value


def _optional_string(
    section: dict[str, Any],
    name: str,
) -> str | None:
    value = section.get(name)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be a string"
        )

    if not value.strip():
        raise ConfigurationValidationError(
            f"Configuration value '{name}' cannot be empty"
        )

    return value


def _optional_int(
    section: dict[str, Any],
    name: str,
) -> int | None:
    value = section.get(name)

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be an integer"
        )

    if value <= 0:
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be positive"
        )

    return value
