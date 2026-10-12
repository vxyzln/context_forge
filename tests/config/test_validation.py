import pytest

from context_forge.config import (
    ConfigurationValidationError,
    ProjectAnalysisConfiguration,
    ProjectConfiguration,
    ProjectStorageConfiguration,
    validate_project_config,
)


def test_validate_project_config_uses_empty_sections_when_missing() -> None:
    result = validate_project_config({})

    assert result == ProjectConfiguration()


def test_validate_project_config_reads_storage_configuration() -> None:
    result = validate_project_config(
        {
            "storage": {
                "database_path": "custom.db",
            }
        }
    )

    assert result.storage == ProjectStorageConfiguration(
        database_path="custom.db",
    )


def test_validate_project_config_reads_analysis_configuration() -> None:
    result = validate_project_config(
        {
            "analysis": {
                "max_context_units": 35,
            }
        }
    )

    assert result.analysis == ProjectAnalysisConfiguration(
        max_context_units=35,
    )


def test_validate_project_config_preserves_partial_configuration() -> None:
    result = validate_project_config(
        {
            "storage": {
                "database_path": "db.sqlite",
            },
        }
    )

    assert result.storage.database_path == "db.sqlite"
    assert result.analysis.max_context_units is None


def test_validate_project_config_rejects_unknown_top_level_section() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Unknown configuration section: extra",
    ):
        validate_project_config({"extra": {}})


def test_validate_project_config_rejects_non_table_section() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration section 'storage' must be a table",
    ):
        validate_project_config({"storage": "invalid"})


def test_validate_project_config_rejects_empty_database_path() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'database_path' cannot be empty",
    ):
        validate_project_config({"storage": {"database_path": "   "}})


def test_validate_project_config_rejects_non_string_database_path() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'database_path' must be a string",
    ):
        validate_project_config({"storage": {"database_path": 123}})


def test_validate_project_config_rejects_non_int_max_context_units() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'max_context_units' must be an integer",
    ):
        validate_project_config({"analysis": {"max_context_units": "20"}})


def test_validate_project_config_rejects_negative_max_context_units() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'max_context_units' must be positive",
    ):
        validate_project_config({"analysis": {"max_context_units": -5}})
