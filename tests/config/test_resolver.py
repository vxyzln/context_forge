from context_forge.config import (
    DEFAULTS,
    ConfigurationDefaults,
    ProjectConfiguration,
    ProjectGenerationConfiguration,
    ProjectProviderConfiguration,
    resolve_configuration,
)


def test_resolve_configuration_uses_defaults_when_layers_are_empty() -> None:
    result = resolve_configuration(
        global_config=ProjectConfiguration(),
        project_config=ProjectConfiguration(),
    )

    assert result == DEFAULTS
    assert result is not DEFAULTS


def test_resolve_configuration_global_overrides_defaults() -> None:
    global_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="global-model",
            base_url="http://global.test",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
            max_tokens=1024,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=ProjectConfiguration(),
    )

    assert result.provider == "deterministic"
    assert result.model == "global-model"
    assert result.base_url == "http://global.test"
    assert result.temperature == 0.5
    assert result.max_tokens == 1024


def test_resolve_configuration_project_overrides_global() -> None:
    global_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="ollama",
            model="global-model",
            base_url="http://global.test",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
            max_tokens=1024,
        ),
    )
    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="project-model",
            base_url="http://project.test",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
            max_tokens=2048,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result.provider == "deterministic"
    assert result.model == "project-model"
    assert result.base_url == "http://project.test"
    assert result.temperature == 0.2
    assert result.max_tokens == 2048


def test_resolve_configuration_merges_partial_project_overrides() -> None:
    global_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="global-model",
            base_url="http://global.test",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
            max_tokens=1024,
        ),
    )
    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            model="project-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result.provider == "deterministic"
    assert result.model == "project-model"
    assert result.base_url == "http://global.test"
    assert result.temperature == 0.2
    assert result.max_tokens == 1024


def test_resolve_configuration_does_not_mutate_inputs() -> None:
    global_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="global-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
            max_tokens=1024,
        ),
    )
    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            model="project-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
        ),
    )

    resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert global_config == ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="global-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
            max_tokens=1024,
        ),
    )
    assert project_config == ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            model="project-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
        ),
    )


def test_resolve_configuration_uses_each_layer_independently() -> None:
    global_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="global-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
        ),
    )

    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            base_url="http://project",
        ),
        generation=ProjectGenerationConfiguration(
            max_tokens=2048,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result == ConfigurationDefaults(
        provider="deterministic",
        model="global-model",
        base_url="http://project",
        temperature=0.5,
        max_tokens=2048,
    )


def test_resolve_configuration_project_values_win_field_by_field() -> None:
    global_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="deterministic",
            model="global-model",
            base_url="http://global",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.7,
            max_tokens=1024,
        ),
    )

    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="ollama",
            model="project-model",
            base_url="http://project",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
            max_tokens=2048,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result == ConfigurationDefaults(
        provider="ollama",
        model="project-model",
        base_url="http://project",
        temperature=0.2,
        max_tokens=2048,
    )
