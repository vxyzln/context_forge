from context_forge.config.defaults import DEFAULTS, ConfigurationDefaults
from context_forge.config.project import ProjectConfiguration


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
