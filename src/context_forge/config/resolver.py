import os
from pathlib import Path

from context_forge.config.defaults import DEFAULTS, ConfigurationDefaults
from context_forge.config.project import ProjectConfiguration
from context_forge.config.validation import ConfigurationValidationError


def normalize_database_path(
    raw_path: str | Path,
    project_root: Path | None = None,
) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        root = (
            Path(os.path.abspath(project_root))
            if project_root is not None
            else Path(os.path.abspath("."))
        )
        path = root / path
    return Path(os.path.normpath(path))


def resolve_project_database_path(
    project_root: Path,
    database_path_override: str | Path | None = None,
    *,
    project_config: ProjectConfiguration | None = None,
    global_config: ProjectConfiguration | None = None,
) -> Path:
    if database_path_override is not None:
        candidate = normalize_database_path(database_path_override, project_root)
        if candidate.is_dir():
            raise ConfigurationValidationError(
                f"Database path cannot be an existing directory: {candidate}"
            )
        return candidate

    if project_config is None:
        from context_forge.config.loading import load_project_configuration

        project_config = load_project_configuration(project_root)

    if global_config is None:
        from context_forge.config.loading import load_global_configuration

        global_config = load_global_configuration()

    resolved = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )
    candidate = normalize_database_path(resolved.database_path, project_root)
    if candidate.is_dir():
        raise ConfigurationValidationError(
            f"Database path cannot be an existing directory: {candidate}"
        )
    return candidate


def resolve_configuration(
    *,
    global_config: ProjectConfiguration,
    project_config: ProjectConfiguration,
) -> ConfigurationDefaults:
    return ConfigurationDefaults(
        database_path=_resolve(
            project_config.storage.database_path,
            global_config.storage.database_path,
            DEFAULTS.database_path,
        ),
        max_context_units=_resolve(
            project_config.analysis.max_context_units,
            global_config.analysis.max_context_units,
            DEFAULTS.max_context_units,
        ),
    )


def _resolve[T](
    project_value: T | None,
    global_value: T | None,
    default_value: T,
) -> T:
    if project_value is not None:
        return project_value

    if global_value is not None:
        return global_value

    return default_value
