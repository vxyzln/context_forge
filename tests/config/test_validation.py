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


def test_validate_project_config_reads_package_policy() -> None:
    cfg = validate_project_config(
        {
            "packages": {
                "default_policy": "allow",
                "rules": [
                    {
                        "source": "src/api",
                        "target": "src/db",
                        "policy": "deny",
                        "rule_id": "NO_API_TO_DB",
                    }
                ],
            }
        }
    )

    assert cfg.packages.default_policy == "allow"
    assert len(cfg.packages.rules) == 1
    assert cfg.packages.rules[0].source_package == "src/api"
    assert cfg.packages.rules[0].target_package == "src/db"
    assert cfg.packages.rules[0].rule_id == "NO_API_TO_DB"


def test_validate_project_config_reads_package_policy_deny_list() -> None:
    cfg = validate_project_config(
        {
            "packages": {
                "deny": ["src/api -> src/db", "src/cli -> src/internal"],
            }
        }
    )

    assert len(cfg.packages.rules) == 2
    assert cfg.packages.rules[0].source_package == "src/api"
    assert cfg.packages.rules[0].target_package == "src/db"
    assert cfg.packages.rules[1].source_package == "src/cli"
    assert cfg.packages.rules[1].target_package == "src/internal"


def test_validate_project_config_default_neutral_policy() -> None:
    cfg = validate_project_config({})
    assert cfg.packages.default_policy == "unrestricted"
    assert len(cfg.packages.rules) == 0


def test_validate_project_config_rejects_duplicate_rule_id() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Duplicate package policy rule_id: 'R1'",
    ):
        validate_project_config(
            {
                "packages": {
                    "rules": [
                        {"source": "src/a", "target": "src/b", "rule_id": "R1"},
                        {"source": "src/c", "target": "src/d", "rule_id": "R1"},
                    ]
                }
            }
        )


def test_validate_project_config_rejects_conflicting_rules() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Conflicting package policy rules for 'src/a -> src/b'",
    ):
        validate_project_config(
            {
                "packages": {
                    "rules": [
                        {"source": "src/a", "target": "src/b", "policy": "allow"},
                        {"source": "src/a", "target": "src/b", "policy": "deny"},
                    ]
                }
            }
        )


def test_validate_project_config_rejects_invalid_default_policy() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Package policy default_policy must be 'unrestricted', 'allow', 'deny', or 'prohibit'",
    ):
        validate_project_config({"packages": {"default_policy": "invalid"}})


def test_validate_project_config_rejects_empty_rule_target() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Package policy rule #1 missing or invalid 'target'",
    ):
        validate_project_config(
            {
                "packages": {
                    "rules": [{"source": "src/a", "target": ""}],
                }
            }
        )


def test_validate_project_config_rejects_invalid_deny_string() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="string must be in format 'source -> target'",
    ):
        validate_project_config(
            {
                "packages": {
                    "deny": ["invalid_format"],
                }
            }
        )
