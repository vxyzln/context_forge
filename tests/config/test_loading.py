from pathlib import Path

import pytest

from context_forge.config import (
    ConfigurationValidationError,
    ProjectAnalysisConfiguration,
    ProjectConfiguration,
    ProjectStorageConfiguration,
    load_global_configuration,
    load_project_configuration,
)


def test_load_project_configuration_returns_empty_configuration_when_missing(
    tmp_path: Path,
) -> None:
    assert load_project_configuration(tmp_path) == ProjectConfiguration()


def test_load_project_configuration_returns_typed_configuration(
    tmp_path: Path,
) -> None:
    (tmp_path / ".contextforge.toml").write_text(
        """
[storage]
database_path = ".context_forge.db"

[analysis]
max_context_units = 50
""",
        encoding="utf-8",
    )

    result = load_project_configuration(tmp_path)

    assert result == ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path=".context_forge.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )


def test_load_project_configuration_validates_loaded_values(
    tmp_path: Path,
) -> None:
    (tmp_path / ".contextforge.toml").write_text(
        """
[analysis]
max_context_units = -5
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'max_context_units' must be positive",
    ):
        load_project_configuration(tmp_path)


def test_load_global_configuration_returns_empty_configuration_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    assert load_global_configuration() == ProjectConfiguration()


def test_load_global_configuration_returns_typed_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[storage]
database_path = "global.db"

[analysis]
max_context_units = 25
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    result = load_global_configuration()

    assert result == ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=25,
        ),
    )


def test_load_global_configuration_validates_loaded_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[analysis]
max_context_units = 0
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'max_context_units' must be positive",
    ):
        load_global_configuration()
