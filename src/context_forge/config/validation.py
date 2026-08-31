from typing import Any

from context_forge.config.project import (
    ProjectConfiguration,
    ProjectGenerationConfiguration,
    ProjectProviderConfiguration,
)


class ConfigurationValidationError(ValueError):
    """Raised when project configuration has an invalid structure or value."""


def validate_project_config(
    data: dict[str, Any],
) -> ProjectConfiguration:
    _validate_top_level(data)

    provider_data = _section(data, "provider")
    generation_data = _section(data, "generation")

    return ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider=_optional_string(provider_data, "provider"),
            model=_optional_string(provider_data, "model"),
            base_url=_optional_string(provider_data, "base_url"),
        ),
        generation=ProjectGenerationConfiguration(
            temperature=_optional_float(generation_data, "temperature"),
            max_tokens=_optional_int(generation_data, "max_tokens"),
        ),
    )


def _validate_top_level(data: dict[str, Any]) -> None:
    allowed = {"provider", "generation"}

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


def _optional_float(
    section: dict[str, Any],
    name: str,
) -> float | None:
    value = section.get(name)

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be a number"
        )

    result = float(value)

    if not 0.0 <= result <= 2.0:
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be between 0.0 and 2.0"
        )

    return result


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
