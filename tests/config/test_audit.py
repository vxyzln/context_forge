from __future__ import annotations

from pathlib import Path

from context_forge.config import (
    DEFAULTS,
    audit_configuration,
)
from context_forge.reporting.contract import DiagnosticSeverity


def test_audit_configuration_defaults_when_no_config(tmp_path: Path) -> None:
    # Both project and global configs missing
    missing_global = tmp_path / "global_missing.toml"
    result = audit_configuration(tmp_path, global_config_path_override=missing_global)

    assert result.is_valid is True
    assert result.status == "default"
    assert result.resolved == DEFAULTS
    assert result.precedence == {
        "database_path": "default",
        "max_context_units": "default",
    }
    assert result.project_config_present is False
    assert result.global_config_present is False
    assert len(result.diagnostics) == 0


def test_audit_configuration_valid_global_only(tmp_path: Path) -> None:
    global_file = tmp_path / "global.toml"
    global_file.write_text(
        """
[storage]
database_path = "global.db"

[analysis]
max_context_units = 50
""",
        encoding="utf-8",
    )

    empty_project = tmp_path / "empty_project"
    empty_project.mkdir()

    result = audit_configuration(empty_project, global_config_path_override=global_file)

    assert result.is_valid is True
    assert result.status == "valid"
    assert result.resolved.database_path == "global.db"
    assert result.resolved.max_context_units == 50
    assert result.precedence == {
        "database_path": "global",
        "max_context_units": "global",
    }
    assert result.global_config_present is True
    assert result.project_config_present is False


def test_audit_configuration_project_overrides_global(tmp_path: Path) -> None:
    global_file = tmp_path / "global.toml"
    global_file.write_text(
        """
[storage]
database_path = "global.db"

[analysis]
max_context_units = 50
""",
        encoding="utf-8",
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_config_file = project_dir / ".contextforge.toml"
    project_config_file.write_text(
        """
[storage]
database_path = "project.db"

[analysis]
max_context_units = 15
""",
        encoding="utf-8",
    )

    result = audit_configuration(project_dir, global_config_path_override=global_file)

    assert result.is_valid is True
    assert result.status == "valid"
    assert result.resolved.database_path == "project.db"
    assert result.resolved.max_context_units == 15
    assert result.precedence == {
        "database_path": "project",
        "max_context_units": "project",
    }
    assert result.project_config_present is True
    assert result.global_config_present is True


def test_audit_configuration_partial_overrides(tmp_path: Path) -> None:
    global_file = tmp_path / "global.toml"
    global_file.write_text(
        """
[storage]
database_path = "global.db"

[analysis]
max_context_units = 50
""",
        encoding="utf-8",
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_config_file = project_dir / ".contextforge.toml"
    # Project overrides only max_context_units; database_path comes from global
    project_config_file.write_text(
        """
[analysis]
max_context_units = 10
""",
        encoding="utf-8",
    )

    result = audit_configuration(project_dir, global_config_path_override=global_file)

    assert result.is_valid is True
    assert result.resolved.database_path == "global.db"
    assert result.resolved.max_context_units == 10
    assert result.precedence == {
        "database_path": "global",
        "max_context_units": "project",
    }


def test_audit_configuration_malformed_project_toml(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".contextforge.toml").write_text(
        "INVALID TOML [[[[[", encoding="utf-8"
    )

    result = audit_configuration(project_dir)

    assert result.is_valid is False
    assert result.status == "invalid"
    assert result.resolved is None
    assert result.precedence == {}
    payload = result.to_dict()
    assert payload["resolved"] is None
    assert payload["precedence"] == {}
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.severity == DiagnosticSeverity.BLOCKER
    assert diag.code == "CONFIG_LOAD_ERROR"
    assert "Invalid project configuration" in diag.message


def test_audit_configuration_malformed_global_toml(tmp_path: Path) -> None:
    global_file = tmp_path / "global.toml"
    global_file.write_text("NOT TOML [[[[", encoding="utf-8")

    result = audit_configuration(global_config_path_override=global_file)

    assert result.is_valid is False
    assert result.status == "invalid"
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == DiagnosticSeverity.BLOCKER
    assert result.diagnostics[0].code == "CONFIG_LOAD_ERROR"


def test_audit_configuration_invalid_structure_unknown_section(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".contextforge.toml").write_text(
        """
[unknown_section]
key = "value"
""",
        encoding="utf-8",
    )

    result = audit_configuration(project_dir)

    assert result.is_valid is False
    assert result.status == "invalid"
    assert any(
        d.code == "CONFIG_VALIDATION_ERROR"
        and "Unknown configuration section" in d.message
        for d in result.diagnostics
    )


def test_audit_configuration_invalid_values(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".contextforge.toml").write_text(
        """
[analysis]
max_context_units = -10
""",
        encoding="utf-8",
    )

    result = audit_configuration(project_dir)

    assert result.is_valid is False
    assert result.status == "invalid"
    assert any(
        d.code == "CONFIG_VALIDATION_ERROR" and "must be positive" in d.message
        for d in result.diagnostics
    )


def test_audit_configuration_config_path_is_directory(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    # Create directory with config filename
    (project_dir / ".contextforge.toml").mkdir()

    result = audit_configuration(project_dir)

    assert result.is_valid is False
    assert result.status == "invalid"
    assert any(
        d.code == "CONFIG_NOT_A_FILE" and "is not a file" in d.message
        for d in result.diagnostics
    )


def test_audit_configuration_to_dict_serialization(tmp_path: Path) -> None:
    result = audit_configuration(tmp_path)
    payload = result.to_dict()

    assert payload["status"] == "default"
    assert "sources" in payload
    assert "resolved" in payload
    assert payload["resolved"]["database_path"] == ".context_forge.db"
    assert payload["resolved"]["max_context_units"] == 20
    assert payload["precedence"]["database_path"] == "default"
    assert payload["precedence"]["max_context_units"] == "default"
    assert isinstance(payload["diagnostics"], list)
