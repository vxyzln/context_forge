from context_forge.config import (
    DEFAULTS,
    ProjectAnalysisConfiguration,
    ProjectConfiguration,
    ProjectStorageConfiguration,
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
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=ProjectConfiguration(),
    )

    assert result.database_path == "global.db"
    assert result.max_context_units == 50


def test_resolve_configuration_project_overrides_global() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )
    project_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="project.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=10,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result.database_path == "project.db"
    assert result.max_context_units == 10


def test_resolve_configuration_merges_partial_project_overrides() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )
    project_config = ProjectConfiguration(
        analysis=ProjectAnalysisConfiguration(
            max_context_units=15,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result.database_path == "global.db"
    assert result.max_context_units == 15


def test_resolve_configuration_does_not_mutate_inputs() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
    )
    project_config = ProjectConfiguration(
        analysis=ProjectAnalysisConfiguration(
            max_context_units=15,
        ),
    )

    resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert global_config == ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
    )
    assert project_config == ProjectConfiguration(
        analysis=ProjectAnalysisConfiguration(
            max_context_units=15,
        ),
    )
