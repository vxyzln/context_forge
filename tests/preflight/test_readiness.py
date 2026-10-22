from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from context_forge.parser.registry import ParserRegistry
from context_forge.preflight import (
    build_preflight_report,
    format_preflight_summary,
)
from context_forge.reporting.contract import DiagnosticSeverity


def test_preflight_valid_python_repository(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main(): pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    report = build_preflight_report(tmp_path)

    assert report["schema_version"] == 1
    assert report["readiness"] in ("ready", "ready_with_limitations")
    assert report["repository_status"]["exists"] is True
    assert report["repository_status"]["is_directory"] is True
    assert report["repository_status"]["is_accessible"] is True
    assert report["inventory"]["directories"] >= 1
    assert report["inventory"]["files"] == 2
    assert report["inventory"]["source_files"] == 1

    py_lang = next((l for l in report["languages"] if l["name"] == "python"), None)
    assert py_lang is not None
    assert py_lang["supported"] is True
    assert py_lang["file_count"] == 1

    assert report["outcome"]["is_success"] is True
    assert report["outcome"]["status"] == "success"


def test_preflight_nonexistent_repository(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing_repo"

    report = build_preflight_report(missing_dir)

    assert report["readiness"] == "blocked"
    assert report["repository_status"]["exists"] is False
    assert report["repository_status"]["is_directory"] is False
    assert report["outcome"]["status"] == "blocked"
    assert report["outcome"]["is_success"] is False
    assert report["outcome"]["summary"]["blockers"] >= 1
    assert report["outcome"]["diagnostics"][0]["code"] == "REPOSITORY_NOT_FOUND"


def test_preflight_file_supplied_instead_of_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("hello", encoding="utf-8")

    report = build_preflight_report(file_path)

    assert report["readiness"] == "blocked"
    assert report["repository_status"]["exists"] is True
    assert report["repository_status"]["is_directory"] is False
    assert report["outcome"]["status"] == "blocked"
    assert report["outcome"]["is_success"] is False
    assert report["outcome"]["diagnostics"][0]["code"] == "REPOSITORY_NOT_A_DIRECTORY"


def test_preflight_inaccessible_directory(tmp_path: Path) -> None:
    with patch("os.listdir", side_effect=PermissionError("Permission denied")):
        report = build_preflight_report(tmp_path)

    assert report["readiness"] == "blocked"
    assert report["repository_status"]["is_accessible"] is False
    assert report["outcome"]["status"] == "blocked"
    assert report["outcome"]["diagnostics"][0]["code"] == "REPOSITORY_INACCESSIBLE"


def test_preflight_detected_unsupported_languages(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "script.js").write_text("console.log(1);\n", encoding="utf-8")
    (tmp_path / "main.rs").write_text("fn main() {}\n", encoding="utf-8")

    report = build_preflight_report(tmp_path)

    assert report["readiness"] == "ready_with_limitations"
    assert report["inventory"]["files"] == 3
    assert report["inventory"]["source_files"] == 3

    py_lang = next(l for l in report["languages"] if l["name"] == "python")
    assert py_lang["supported"] is True

    js_lang = next(l for l in report["languages"] if l["name"] == "javascript")
    assert js_lang["supported"] is False

    rs_lang = next(l for l in report["languages"] if l["name"] == "rust")
    assert rs_lang["supported"] is False

    assert any(
        d["code"] == "UNSUPPORTED_LANGUAGE"
        and d["severity"] == "warning"
        and "javascript" in d["message"]
        for d in report["outcome"]["diagnostics"]
    )
    assert any("not supported for AST parsing" in lim for lim in report["limitations"])


def test_preflight_with_custom_parser_registry(tmp_path: Path) -> None:
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")

    empty_registry = ParserRegistry()
    report = build_preflight_report(tmp_path, parser_registry=empty_registry)

    py_lang = next(l for l in report["languages"] if l["name"] == "python")
    assert py_lang["supported"] is False
    assert any(
        d["code"] == "NO_SUPPORTED_SOURCES" for d in report["outcome"]["diagnostics"]
    )


def test_preflight_excludes_standard_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")

    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("dummy", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("dummy", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.cpython.pyc").write_text("dummy", encoding="utf-8")

    report = build_preflight_report(tmp_path)

    assert report["inventory"]["files"] == 1
    assert report["inventory"]["directories"] == 2
    assert report["repository_status"]["is_git_repository"] is True


def test_git_detection_standard_git_directory(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    report = build_preflight_report(tmp_path)

    assert report["repository_status"]["is_git_repository"] is True
    assert not any("not a Git repository" in lim for lim in report["limitations"])


def test_git_detection_worktree_file_metadata(tmp_path: Path) -> None:
    main_git_dir = tmp_path / "main_repo_git"
    main_git_dir.mkdir()

    worktree_dir = tmp_path / "worktree_repo"
    worktree_dir.mkdir()
    (worktree_dir / "app.py").write_text("x = 1\n", encoding="utf-8")
    (worktree_dir / ".git").write_text(f"gitdir: {main_git_dir}\n", encoding="utf-8")

    report = build_preflight_report(worktree_dir)

    assert report["repository_status"]["is_git_repository"] is True
    assert not any("not a Git repository" in lim for lim in report["limitations"])


def test_git_detection_non_git_directory(tmp_path: Path) -> None:
    repo_dir = tmp_path / "plain_dir"
    repo_dir.mkdir()
    (repo_dir / "app.py").write_text("x = 1\n", encoding="utf-8")

    report = build_preflight_report(repo_dir)

    assert report["repository_status"]["is_git_repository"] is False
    assert any(
        "Directory is not a Git repository" in lim for lim in report["limitations"]
    )


def test_git_detection_malformed_git_file(tmp_path: Path) -> None:

    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    (repo1 / ".git").write_text("", encoding="utf-8")
    assert (
        build_preflight_report(repo1)["repository_status"]["is_git_repository"] is False
    )

    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    (repo2 / ".git").write_text("not a git repository\n", encoding="utf-8")
    assert (
        build_preflight_report(repo2)["repository_status"]["is_git_repository"] is False
    )

    repo3 = tmp_path / "repo3"
    repo3.mkdir()
    (repo3 / ".git").write_text("gitdir: /nonexistent/target/path\n", encoding="utf-8")
    assert (
        build_preflight_report(repo3)["repository_status"]["is_git_repository"] is False
    )


def test_preflight_invalid_config_does_not_claim_resolved(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".contextforge.toml").write_text("INVALID [[[[", encoding="utf-8")

    report = build_preflight_report(tmp_path)

    assert report["configuration"]["status"] == "invalid"
    assert report["configuration"]["resolved"] is None
    assert report["configuration"]["precedence"] == {}
    assert report["readiness"] == "blocked"


def test_preflight_with_valid_and_invalid_configuration(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    config_file = tmp_path / ".contextforge.toml"
    config_file.write_text(
        """
[storage]
database_path = "custom_path.db"

[analysis]
max_context_units = 30
""",
        encoding="utf-8",
    )

    valid_report = build_preflight_report(tmp_path)
    assert valid_report["configuration"]["status"] == "valid"
    assert (
        valid_report["configuration"]["resolved"]["database_path"] == "custom_path.db"
    )
    assert valid_report["configuration"]["resolved"]["max_context_units"] == 30
    assert valid_report["configuration"]["precedence"]["database_path"] == "project"
    assert valid_report["readiness"] != "blocked"

    config_file.write_text("MALFORMED [[[[", encoding="utf-8")
    invalid_report = build_preflight_report(tmp_path)
    assert invalid_report["configuration"]["status"] == "invalid"
    assert invalid_report["readiness"] == "blocked"
    assert invalid_report["outcome"]["status"] == "blocked"
    assert any(
        d["code"] == "CONFIG_LOAD_ERROR"
        and d["severity"] == DiagnosticSeverity.BLOCKER.value
        for d in invalid_report["outcome"]["diagnostics"]
    )


def test_preflight_read_only_guarantee_no_side_effects(tmp_path: Path) -> None:

    src = tmp_path / "src"
    src.mkdir()
    py_file = src / "app.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    initial_files = set(tmp_path.rglob("*"))
    initial_mtimes = {f: f.stat().st_mtime_ns for f in initial_files if f.is_file()}

    report = build_preflight_report(tmp_path)

    assert report["analysis_readiness"]["has_persisted_analysis"] is False
    assert report["analysis_readiness"]["database_path"] == ".context_forge.db"

    db_file = tmp_path / ".context_forge.db"
    assert not db_file.exists(), "Preflight must not create .context_forge.db"

    final_files = set(tmp_path.rglob("*"))
    assert final_files == initial_files, "Preflight must not create any files or dirs"

    final_mtimes = {f: f.stat().st_mtime_ns for f in final_files if f.is_file()}
    assert final_mtimes == initial_mtimes, "Preflight must not touch file timestamps"


def test_format_preflight_summary(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    report = build_preflight_report(tmp_path)

    lines = format_preflight_summary(report)
    text = "\n".join(lines)

    assert f"Repository: {tmp_path.resolve()}" in text
    assert "Readiness: READY" in text
    assert "Repository status:" in text
    assert "Configuration:" in text
    assert "Inventory:" in text
    assert "Analysis readiness:" in text
    assert "Limitations:" in text
