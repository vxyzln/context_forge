from context_forge.config.defaults import DEFAULTS, ConfigurationDefaults
from context_forge.config.project import ProjectConfiguration


def resolve_configuration(
    *,
    global_config: ProjectConfiguration,
    project_config: ProjectConfiguration,
) -> ConfigurationDefaults:
    return ConfigurationDefaults(
        provider=_resolve(
            project_config.provider.provider,
            global_config.provider.provider,
            DEFAULTS.provider,
        ),
        model=_resolve(
            project_config.provider.model,
            global_config.provider.model,
            DEFAULTS.model,
        ),
        base_url=_resolve(
            project_config.provider.base_url,
            global_config.provider.base_url,
            DEFAULTS.base_url,
        ),
        temperature=_resolve(
            project_config.generation.temperature,
            global_config.generation.temperature,
            DEFAULTS.temperature,
        ),
        max_tokens=_resolve(
            project_config.generation.max_tokens,
            global_config.generation.max_tokens,
            DEFAULTS.max_tokens,
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
