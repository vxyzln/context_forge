import json
import sqlite3
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from context_forge.context.models import ContextPackage, ContextUnit
from context_forge.main import (
    load_fresh_project,
    load_project_analysis,
    main,
    parse_args,
    resolve_project_path,
    run_cache,
    run_diagnostics,
    run_inspect,
    run_status,
)
from context_forge.query.result import SearchResult, SearchResultType


def test_main_without_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["context-forge"]),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
    ):
        main()

    captured = capsys.readouterr()

    assert "usage: context-forge" in captured.out
    assert "analyze" in captured.out
    assert "refresh" in captured.out
    assert "context" in captured.out
    assert "status" in captured.out
    assert "cache" in captured.out
    assert "inspect" in captured.out
    assert "diagnostics" in captured.out
    assert "memory" in captured.out
    assert "architecture" in captured.out
    assert "impact" in captured.out
    assert "health" in captured.out
    assert "inspect-change" in captured.out
    assert "generate" not in captured.out
    assert "runtime" not in captured.out
    assert "--provider" not in captured.out
    assert captured.err == ""
    analyzer.assert_not_called()


def test_resolve_project_path_returns_resolved_directory(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    nested_path = project_path / ".." / "project"

    assert resolve_project_path(nested_path) == project_path.resolve()


def test_resolve_project_path_expands_user_directory(tmp_path: Path) -> None:
    with patch("context_forge.main.Path.expanduser", return_value=tmp_path):
        assert resolve_project_path(Path("~/project")) == tmp_path.resolve()


def test_resolve_project_path_rejects_missing_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(
        ValueError,
        match=r"Project path does not exist: .*missing",
    ):
        resolve_project_path(missing_path)


def test_resolve_project_path_rejects_file(tmp_path: Path) -> None:
    project_file = tmp_path / "project.py"
    project_file.write_text("print('hello')")

    with pytest.raises(
        ValueError,
        match=r"Project path is not a directory: .*project\.py",
    ):
        resolve_project_path(project_file)


def test_main_reports_missing_project_path_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_path = tmp_path / "missing"

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "status", str(missing_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == f"Error: Project path does not exist: {missing_path.resolve()}\n"
    )


def test_main_reports_file_project_path_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_file = tmp_path / "project.py"
    project_file.write_text("print('hello')")

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "status", str(project_file)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        captured.err
        == f"Error: Project path is not a directory: {project_file.resolve()}\n"
    )


def test_parse_args_subcommands():
    args = parse_args(["analyze", "/tmp/project"])
    assert args.command == "analyze"
    assert args.path == Path("/tmp/project")

    args = parse_args(["status", "/tmp/project"])
    assert args.command == "status"
    assert args.path == Path("/tmp/project")

    args = parse_args(["cache", "/tmp/project"])
    assert args.command == "cache"
    assert args.path == Path("/tmp/project")

    args = parse_args(["inspect", "/tmp/project"])
    assert args.command == "inspect"
    assert args.path == Path("/tmp/project")

    args = parse_args(["diagnostics", "/tmp/project"])
    assert args.command == "diagnostics"
    assert args.path == Path("/tmp/project")

    args = parse_args(["memory", "inspect", "/tmp/project"])
    assert args.command == "memory"
    assert args.memory_command == "inspect"
    assert args.path == Path("/tmp/project")

    args = parse_args(["refresh", "/tmp/project"])
    assert args.command == "refresh"
    assert args.path == Path("/tmp/project")

    args = parse_args(["refresh"])
    assert args.command == "refresh"
    assert args.path == Path(".")

    args = parse_args(["memory", "search", "Calculator.hello", "/tmp/project"])
    assert args.command == "memory"
    assert args.memory_command == "search"
    assert args.query == "Calculator.hello"
    assert args.path == Path("/tmp/project")

    args = parse_args(["memory", "search", "Calculator"])
    assert args.command == "memory"
    assert args.memory_command == "search"
    assert args.query == "Calculator"
    assert args.path == Path(".")

    args = parse_args(
        ["context", "/tmp/project", "--task", "Fix bugs", "--output", "out.json"]
    )
    assert args.command == "context"
    assert args.path == Path("/tmp/project")
    assert args.task == "Fix bugs"
    assert args.output == Path("out.json")


def test_memory_inspect_command_reuses_existing_inspection(
    tmp_path: Path,
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "memory", "inspect", str(tmp_path)],
        ),
        patch("context_forge.main.run_inspect") as run_inspect_mock,
    ):
        main()

    run_inspect_mock.assert_called_once_with(tmp_path)


def test_legacy_inspect_command_remains_supported(
    tmp_path: Path,
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "inspect", str(tmp_path)],
        ),
        patch("context_forge.main.run_inspect") as run_inspect_mock,
    ):
        main()

    run_inspect_mock.assert_called_once_with(tmp_path)


def test_parse_args_bare_path_defaults_to_status():
    args = parse_args(["/tmp/project"])
    assert args.command == "status"
    assert args.path == Path("/tmp/project")


def test_analyze_command_prints_repository_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {
            "root_path": Path("/tmp/project"),
            "files": [1, 2, 3],
            "symbols": [1, 2],
            "relationships": [1, 2, 3, 4],
            "analysis_status": "analyzed",
        },
    )()

    with (
        patch.object(sys, "argv", ["context-forge", "analyze", "."]),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
        patch("context_forge.operational_logging.log_analysis_started") as log_started,
        patch(
            "context_forge.operational_logging.log_analysis_completed"
        ) as log_completed,
    ):
        analyzer.return_value.analyze.return_value = project
        main()

    captured = capsys.readouterr()

    assert captured.out == (
        "Analyzed: /tmp/project\n"
        "Files: 3\n"
        "Symbols: 2\n"
        "Relationships: 4\n"
        "Status: analyzed\n"
    )
    assert captured.err == ""
    log_started.assert_called_once()
    log_completed.assert_called_once()


def test_analyze_command_reports_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "analyze", "."]),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
        patch("context_forge.operational_logging.log_analysis_failed") as log_failed,
        pytest.raises(SystemExit) as exc_info,
    ):
        analyzer.return_value.analyze.side_effect = RuntimeError("AST parse error")
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: AST parse error\n"
    log_failed.assert_called_once()


def test_run_status_does_not_analyze(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("status must not analyze the repository")

    with patch("context_forge.main.ProjectAnalyzer.analyze", fail_if_called):

        class FakeFreshness:
            is_fresh = True

        class FakeRepository:
            def check_cache_freshness(self, repository_key, fingerprints):
                return FakeFreshness()

        project = type(
            "Project",
            (),
            {
                "root_path": tmp_path,
                "name": "sample-repo",
                "analysis_status": "analyzed",
                "project_type": "python",
                "files": [1],
                "symbols": [1, 2],
                "relationships": [],
                "errors": [],
            },
        )()

        metadata = type(
            "Metadata",
            (),
            {
                "cache_schema_version": 1,
                "analyzer_version": "0.1.0",
            },
        )()

        with (
            patch(
                "context_forge.main.load_project_analysis",
                return_value=(FakeRepository(), "key", project, metadata),
            ),
            patch("context_forge.main.current_fingerprints", return_value={}),
        ):
            run_status(tmp_path)

        captured = capsys.readouterr()
        assert "Repository: " in captured.out
        assert "Project: sample-repo" in captured.out
        assert "Cache status: fresh" in captured.out
        assert "Cache schema version:" not in captured.out
        assert "Analyzer version:" not in captured.out


def test_run_cache_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    class Changes:
        added = ("file_a.py",)
        modified = ("file_b.py",)
        deleted = ("file_c.py",)

    class StaleFreshness:
        is_fresh = False
        reason = "Files were modified"
        changes = Changes()

    class FakeRepository:
        def check_cache_freshness(self, repository_key, fingerprints):
            return StaleFreshness()

    project = type(
        "Project",
        (),
        {
            "root_path": tmp_path,
            "name": "sample-repo",
            "analysis_status": "analyzed",
            "project_type": "python",
            "files": [],
            "symbols": [],
            "relationships": [],
            "errors": [],
        },
    )()

    metadata = type(
        "Metadata",
        (),
        {
            "cache_schema_version": 1,
            "analyzer_version": "0.1.0",
        },
    )()

    with (
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(FakeRepository(), "sample-key", project, metadata),
        ),
        patch(
            "context_forge.main.current_fingerprints",
            return_value={"file_b.py": "hash"},
        ),
    ):
        run_cache(tmp_path)

    captured = capsys.readouterr()
    assert "Repository: sample-key" in captured.out
    assert "Cache status: stale" in captured.out
    assert "Cache schema version:" not in captured.out
    assert "Analyzer version:" not in captured.out
    assert "Added paths: 1" in captured.out
    assert "Modified paths: 1" in captured.out
    assert "Deleted paths: 1" in captured.out
    assert "  file_a.py" in captured.out
    assert "  file_b.py" in captured.out
    assert "  file_c.py" in captured.out


def test_run_inspect_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file_obj = type("File", (), {"path": "auth/login.py"})()
    symbol_obj = type(
        "Symbol",
        (),
        {
            "file_id": 1,
            "start_line": 10,
            "end_line": 20,
            "name": "login",
            "qualified_name": "auth.login",
            "kind": "function",
        },
    )()
    rel_type = type("RelType", (), {"value": "imports"})()
    rel_obj = type(
        "Rel",
        (),
        {
            "relationship_type": rel_type,
            "source_id": "auth.login",
            "target_id": "hashlib",
        },
    )()

    project = type(
        "Project",
        (),
        {
            "root_path": tmp_path,
            "files": [file_obj],
            "symbols": [symbol_obj],
            "relationships": [rel_obj],
        },
    )()

    with patch(
        "context_forge.main.load_project_analysis",
        return_value=(None, "key", project, None),
    ):
        run_inspect(tmp_path)

    captured = capsys.readouterr()
    assert "Files:" in captured.out
    assert "  auth/login.py" in captured.out
    assert "Symbols:" in captured.out
    assert "  auth.login [function] lines 10-20" in captured.out
    assert "Relationships:" in captured.out
    assert "  imports: auth.login -> hashlib" in captured.out


def test_run_diagnostics_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error_obj = type(
        "Error",
        (),
        {
            "severity": "error",
            "message": "Syntax error at token",
            "path": "broken.py",
            "line": 15,
        },
    )()

    project = type(
        "Project",
        (),
        {
            "root_path": tmp_path,
            "errors": [error_obj],
        },
    )()

    with patch(
        "context_forge.main.load_project_analysis",
        return_value=(None, "key", project, None),
    ):
        run_diagnostics(tmp_path)

    captured = capsys.readouterr()
    assert "[error] Syntax error at token" in captured.out
    assert "  Path: broken.py" in captured.out
    assert "  Line: 15" in captured.out


def test_load_project_analysis_requires_persisted_analysis(tmp_path: Path) -> None:
    with (
        patch(
            "context_forge.main.ProjectRepository.load_analysis",
            return_value=None,
        ),
        pytest.raises(
            ValueError,
            match="No persisted analysis found; run 'context-forge analyze' first",
        ),
    ):
        load_project_analysis(tmp_path)


def test_load_fresh_project_rejects_stale_analysis(tmp_path: Path) -> None:
    project = type("Project", (), {"root_path": tmp_path, "files": []})()
    metadata = type("Metadata", (), {})()

    class StaleFreshness:
        is_fresh = False

    class FakeRepository:
        def check_cache_freshness(self, repository_key, fingerprints):
            return StaleFreshness()

    with (
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(FakeRepository(), "key", project, metadata),
        ),
        patch("context_forge.main.current_fingerprints", return_value={}),
        pytest.raises(
            ValueError,
            match=r"Repository analysis is stale; run 'context-forge analyze .*' first",
        ),
    ):
        load_fresh_project(tmp_path)


def test_context_command_with_explicit_task(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import uuid

    from context_forge.context.types import ContextUnitType

    unit_id = uuid.uuid4()
    package = ContextPackage(
        task="Authenticate users",
        units=(
            ContextUnit(
                entity_id=unit_id,
                unit_type=ContextUnitType.FILE,
                relevance=1.0,
                content="def auth(): pass",
            ),
        ),
    )

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "context", str(tmp_path), "--task", "Authenticate users"],
        ),
        patch(
            "context_forge.main.load_fresh_project", return_value=(object(), object())
        ),
        patch("context_forge.application.build_context_service") as build_service,
    ):
        build_service.return_value.retrieve_context.return_value = package
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    assert parsed["task"] == "Authenticate users"
    assert parsed["units"][0]["entity_id"] == str(unit_id)
    assert parsed["units"][0]["unit_type"] == "file"


def test_context_command_writes_output_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = ContextPackage(
        task="Explain auth",
        units=(),
    )
    output_file = tmp_path / "context.json"

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "context",
                str(tmp_path),
                "--task",
                "Explain auth",
                "--output",
                str(output_file),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project", return_value=(object(), object())
        ),
        patch("context_forge.application.build_context_service") as build_service,
    ):
        build_service.return_value.retrieve_context.return_value = package
        main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert output_file.exists()
    content = json.loads(output_file.read_text(encoding="utf-8"))
    assert content["task"] == "Explain auth"


def test_context_command_interactive_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = ContextPackage(
        task="Fix scrolling",
        units=(),
    )

    with (
        patch.object(sys, "argv", ["context-forge", "context", str(tmp_path)]),
        patch(
            "context_forge.main.load_fresh_project", return_value=(object(), object())
        ),
        patch("builtins.input", return_value="Fix scrolling"),
        patch("context_forge.application.build_context_service") as build_service,
    ):
        build_service.return_value.retrieve_context.return_value = package
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    parsed = json.loads(captured.out)
    assert parsed["task"] == "Fix scrolling"


def test_context_command_rejects_empty_task(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "context", str(tmp_path), "--task", "   "],
        ),
        patch(
            "context_forge.main.load_fresh_project", return_value=(object(), object())
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.err == "Error: Task cannot be empty\n"


def test_context_command_handles_keyboard_interrupt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "context", str(tmp_path)]),
        patch(
            "context_forge.main.load_fresh_project", return_value=(object(), object())
        ),
        patch("builtins.input", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 130
    captured = capsys.readouterr()
    assert captured.out == ""


def test_context_command_handles_eof(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "context", str(tmp_path)]),
        patch(
            "context_forge.main.load_fresh_project", return_value=(object(), object())
        ),
        patch("builtins.input", side_effect=EOFError),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.err == "Error: Task input ended unexpectedly\n"


def test_cli_entry_points_share_the_same_application() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_config = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    scripts = project_config["project"]["scripts"]

    assert scripts["context-forge"] == "context_forge.main:main"
    assert scripts["cf"] == scripts["context-forge"]


@pytest.mark.parametrize(
    "argv",
    [
        ["memory"],
        ["memory", "unknown"],
        ["status", "--unknown"],
        ["context", "--unknown"],
        ["architecture", "--unknown"],
        ["impact", "tgt", "--unknown"],
        ["health", "--unknown"],
        ["memory", "dependencies", "main.py", "--unknown"],
    ],
)
def test_main_rejects_invalid_arguments_before_dispatch(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", *argv]),
        patch("context_forge.main._dispatch_command") as dispatch_mock,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 2
    assert "error:" in capsys.readouterr().err
    dispatch_mock.assert_not_called()


@pytest.mark.parametrize(
    ("argv", "handler_name"),
    [
        (["status", "."], "run_status"),
        (["memory", "inspect", "."], "run_inspect"),
        (["memory", "search", "Calculator", "."], "run_memory_search"),
        (["memory", "file", "main.py", "."], "run_memory_file"),
        (["memory", "symbol", "Calculator", "."], "run_memory_symbol"),
        (
            ["memory", "references", "Calculator", "."],
            "run_memory_references",
        ),
        (
            ["memory", "relationships", "Calculator", "."],
            "run_memory_relationships",
        ),
        (
            ["memory", "dependencies", "main.py", "."],
            "run_memory_dependencies",
        ),
        (["architecture", "."], "run_architecture"),
        (["impact", "Calculator", "."], "run_impact"),
        (["health", "."], "run_health"),
        (["locate", "Calculator", "."], "run_locate"),
    ],
)
def test_command_dispatch_reports_execution_errors(
    argv: list[str],
    handler_name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", *argv]),
        patch(
            f"context_forge.main.{handler_name}",
            side_effect=RuntimeError("operation failed"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: operation failed\n"


def test_status_reports_uninitialized_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "status", str(tmp_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "Error: No persisted analysis found; run 'context-forge analyze' first\n"
    )


def test_refresh_command_reuses_analyze_handler(
    tmp_path: Path,
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "refresh", str(tmp_path)],
        ),
        patch("context_forge.main.run_analyze") as run_analyze_mock,
    ):
        main()

    run_analyze_mock.assert_called_once_with(tmp_path)


def test_memory_search_prints_ranked_results(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SearchResult(
        result_type=SearchResultType.SYMBOL,
        entity_id=UUID(int=1),
        name="hello",
        path="src/calculator.py",
        score=0.95,
        reason="Exact qualified symbol name match",
        qualified_name="Calculator.hello",
    )

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "search",
                "Calculator.hello",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(object(), object()),
        ) as load_project_mock,
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.search.return_value = [result]
        main()

    load_project_mock.assert_called_once_with(tmp_path.resolve())
    query_mock.return_value.search.assert_called_once_with("Calculator.hello")

    captured = capsys.readouterr()

    assert captured.err == ""
    assert f"Repository: {tmp_path.resolve()}" in captured.out
    assert "Query: Calculator.hello" in captured.out
    assert "Results: 1" in captured.out
    assert "[symbol] Calculator.hello" in captured.out
    assert "Path: src/calculator.py" in captured.out
    assert "Score: 0.95" in captured.out
    assert "Match: Exact qualified symbol name match" in captured.out


def test_memory_search_reports_no_matches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "search",
                "nonexistent_entity",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(object(), object()),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.search.return_value = []
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Results: 0" in captured.out
    assert "No matches found." in captured.out


def test_memory_search_rejects_blank_query(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "search",
                "   ",
                str(tmp_path),
            ],
        ),
        patch("context_forge.main.load_fresh_project") as load_project_mock,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: Search query cannot be empty\n"

    load_project_mock.assert_not_called()


def test_parse_memory_file_and_symbol_commands() -> None:
    args = parse_args(["memory", "file", "src/main.py"])

    assert args.command == "memory"
    assert args.memory_command == "file"
    assert args.file_path == "src/main.py"
    assert args.path == Path(".")

    args = parse_args(["memory", "file", "src/main.py", "/tmp/project"])

    assert args.file_path == "src/main.py"
    assert args.path == Path("/tmp/project")

    args = parse_args(["memory", "symbol", "Calculator"])

    assert args.command == "memory"
    assert args.memory_command == "symbol"
    assert args.symbol_name == "Calculator"
    assert args.path == Path(".")

    args = parse_args(["memory", "symbol", "hello", "/tmp/project"])

    assert args.symbol_name == "hello"
    assert args.path == Path("/tmp/project")


def test_memory_file_reports_missing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "file",
                "missing.py",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(type("Project", (), {"files": [], "symbols": []})(), None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = None
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "File: missing.py" in captured.out
    assert "File not found." in captured.out


def test_memory_symbol_reports_all_matching_definitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_one = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("main.py"),
        },
    )()
    file_two = type(
        "File",
        (),
        {
            "id": UUID(int=2),
            "path": Path("utils.py"),
        },
    )()

    symbol_one = type(
        "Symbol",
        (),
        {
            "file_id": file_one.id,
            "name": "hello",
            "qualified_name": "Calculator.hello",
            "kind": "function",
            "start_line": 7,
            "end_line": 8,
            "signature": "hello(self)",
        },
    )()
    symbol_two = type(
        "Symbol",
        (),
        {
            "file_id": file_two.id,
            "name": "hello",
            "qualified_name": "hello",
            "kind": "function",
            "start_line": 1,
            "end_line": 2,
            "signature": None,
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [file_one, file_two],
            "symbols": [symbol_one, symbol_two],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "symbol",
                "hello",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.find_symbols.return_value = [
            symbol_one,
            symbol_two,
        ]
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Matches: 2" in captured.out
    assert "Multiple definitions found:" in captured.out
    assert "Path: main.py" in captured.out
    assert "Path: utils.py" in captured.out
    assert "Lines: 7-8" in captured.out
    assert "Lines: 1-2" in captured.out
    assert "Signature: hello(self)" in captured.out


def test_memory_symbol_rejects_blank_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "symbol",
                "   ",
                str(tmp_path),
            ],
        ),
        patch("context_forge.main.load_fresh_project") as load_project_mock,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Symbol name cannot be empty\n"
    load_project_mock.assert_not_called()


def test_memory_file_displays_metadata_and_symbols(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "name": "main.py",
            "extension": ".py",
            "file_type": type("FileType", (), {"value": "source"})(),
            "size": 128,
        },
    )()

    symbol = type(
        "Symbol",
        (),
        {
            "name": "Calculator",
            "qualified_name": "Calculator",
            "kind": "class",
            "start_line": 1,
            "end_line": 10,
            "signature": "class Calculator",
        },
    )()

    project = type(
        "Project",
        (),
        {"files": [file], "symbols": [symbol]},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "file",
                "main.py",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = file
        query_mock.return_value.find_symbols_in_file.return_value = [symbol]
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "File: main.py" in captured.out
    assert "Name: main.py" in captured.out
    assert "Extension: .py" in captured.out
    assert "Size: 128 bytes" in captured.out
    assert "Symbols: 1" in captured.out
    assert "[class] Calculator" in captured.out
    assert "Lines: 1-10" in captured.out
    assert "Signature: class Calculator" in captured.out

    query_mock.return_value.get_file.assert_called_once_with("main.py")
    query_mock.return_value.find_symbols_in_file.assert_called_once_with(file.id)


def test_memory_symbol_resolves_qualified_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_one = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("main.py"),
        },
    )()
    file_two = type(
        "File",
        (),
        {
            "id": UUID(int=2),
            "path": Path("utils.py"),
        },
    )()

    symbol_one = type(
        "Symbol",
        (),
        {
            "file_id": file_one.id,
            "name": "hello",
            "qualified_name": "Calculator.hello",
            "kind": "method",
            "start_line": 7,
            "end_line": 8,
            "signature": "hello(self)",
        },
    )()
    symbol_two = type(
        "Symbol",
        (),
        {
            "file_id": file_two.id,
            "name": "hello",
            "qualified_name": "hello",
            "kind": "function",
            "start_line": 1,
            "end_line": 2,
            "signature": None,
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [file_one, file_two],
            "symbols": [symbol_one, symbol_two],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "symbol",
                "Calculator.hello",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.find_symbols_by_qualified_name.return_value = [
            symbol_one,
        ]
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Symbol: Calculator.hello" in captured.out
    assert "Matches: 1" in captured.out
    assert "[method] Calculator.hello" in captured.out
    assert "Path: main.py" in captured.out
    assert "Lines: 7-8" in captured.out
    assert "Signature: hello(self)" in captured.out
    assert "utils.py" not in captured.out

    query_mock.return_value.find_symbols_by_qualified_name.assert_called_once_with(
        "Calculator.hello",
    )


def test_parse_memory_references_and_relationships_commands() -> None:
    args = parse_args(["memory", "references", "Calculator.hello"])

    assert args.command == "memory"
    assert args.memory_command == "references"
    assert args.symbol_name == "Calculator.hello"
    assert args.path == Path(".")

    args = parse_args(
        [
            "memory",
            "relationships",
            "src/main.py",
            "/tmp/project",
            "--direction",
            "incoming",
            "--type",
            "references",
        ]
    )

    assert args.command == "memory"
    assert args.memory_command == "relationships"
    assert args.entity_name == "src/main.py"
    assert args.path == Path("/tmp/project")
    assert args.direction == "incoming"
    assert args.relationship_type == "references"


def test_memory_relationships_reports_no_relationships(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("main.py"),
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [file],
            "symbols": [],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "relationships",
                "main.py",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = file
        query_mock.return_value.get_relationships.return_value = []
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Entity type: file" in captured.out
    assert "Relationships: 0" in captured.out
    assert "No relationships found." in captured.out


def test_memory_references_reports_missing_symbol(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {
            "files": [],
            "symbols": [],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "references",
                "missing_symbol",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.find_symbols.return_value = []
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Matches: 0" in captured.out
    assert "No matching symbol found." in captured.out


def test_memory_references_displays_indexed_reference(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("src/main.py"),
        },
    )()

    symbol = type(
        "Symbol",
        (),
        {
            "id": UUID(int=2),
            "file_id": source_file.id,
            "name": "calculate",
            "qualified_name": "Calculator.calculate",
            "kind": "function",
            "start_line": 10,
            "end_line": 20,
        },
    )()

    relationship = type(
        "Relationship",
        (),
        {
            "id": UUID(int=3),
            "source_id": source_file.id,
            "target_id": symbol.id,
            "relationship_type": "references",
            "confidence": 0.9,
            "metadata": {
                "line": "invalid",
                "name": "calculate",
                "qualified_name": "Calculator.calculate",
            },
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [source_file],
            "symbols": [symbol],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "references",
                "calculate",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.find_symbols.return_value = [symbol]
        query_mock.return_value.get_incoming_relationships.return_value = [relationship]

        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Matches: 1" in captured.out
    assert "References: 1" in captured.out
    assert "Path: src/main.py" in captured.out
    assert "Line: invalid" in captured.out
    assert "Reference: calculate" in captured.out
    assert "Qualified name: Calculator.calculate" in captured.out
    assert "Confidence: 0.90" in captured.out

    query_mock.return_value.get_incoming_relationships.assert_called_once_with(
        symbol.id,
        relationship_type="references",
    )


def test_memory_relationships_displays_indexed_relationship(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("src/main.py"),
        },
    )()

    symbol = type(
        "Symbol",
        (),
        {
            "id": UUID(int=2),
            "file_id": source_file.id,
            "name": "calculate",
            "qualified_name": "Calculator.calculate",
            "kind": "function",
        },
    )()

    relationship = type(
        "Relationship",
        (),
        {
            "id": UUID(int=3),
            "source_id": source_file.id,
            "target_id": symbol.id,
            "relationship_type": "defines",
            "confidence": 1.0,
            "metadata": {
                "line": "10",
                "qualified_name": "Calculator.calculate",
            },
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [source_file],
            "symbols": [symbol],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "relationships",
                "src/main.py",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = source_file
        query_mock.return_value.get_relationships.return_value = [relationship]

        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "Entity type: file" in captured.out
    assert "Relationships: 1" in captured.out
    assert "[defines] [file] src/main.py -> [function] Calculator.calculate" in (
        captured.out
    )
    assert "Confidence: 1.00" in captured.out
    assert "Line: 10" in captured.out
    assert "Qualified name: Calculator.calculate" in captured.out

    query_mock.return_value.get_relationships.assert_called_once_with(
        source_file.id,
        relationship_type=None,
    )


@pytest.mark.parametrize(
    ("direction", "method_name"),
    [
        ("incoming", "get_incoming_relationships"),
        ("outgoing", "get_outgoing_relationships"),
        ("both", "get_relationships"),
    ],
)
def test_memory_relationships_applies_direction_and_type(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    direction: str,
    method_name: str,
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("main.py"),
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [file],
            "symbols": [],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "relationships",
                "main.py",
                str(tmp_path),
                "--direction",
                direction,
                "--type",
                "references",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = file
        getattr(query_mock.return_value, method_name).return_value = []

        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert f"Direction: {direction}" in captured.out
    assert "Relationship type: references" in captured.out
    assert "Relationships: 0" in captured.out

    getattr(
        query_mock.return_value,
        method_name,
    ).assert_called_once_with(
        file.id,
        relationship_type="references",
    )


def test_output_format_defaults_to_text() -> None:
    from context_forge.main import parse_args

    commands = [
        ["analyze"],
        ["refresh"],
        ["status"],
        ["cache"],
        ["inspect"],
        ["memory", "inspect"],
        ["memory", "search", "Calculator"],
        ["memory", "file", "src/calculator.py"],
        ["memory", "symbol", "Calculator"],
        ["memory", "references", "Calculator"],
        ["memory", "relationships", "src/calculator.py"],
        ["memory", "dependencies", "src/calculator.py"],
        ["diagnostics"],
        ["locate", "Calculator"],
    ]

    for command in commands:
        args = parse_args(command)
        assert args.format == "text"


def test_output_format_accepts_json() -> None:
    from context_forge.main import parse_args

    commands = [
        ["analyze"],
        ["refresh"],
        ["status"],
        ["cache"],
        ["inspect"],
        ["memory", "inspect"],
        ["memory", "search", "Calculator"],
        ["memory", "file", "src/calculator.py"],
        ["memory", "symbol", "Calculator"],
        ["memory", "references", "Calculator"],
        ["memory", "relationships", "src/calculator.py"],
        ["memory", "dependencies", "src/calculator.py"],
        ["diagnostics"],
        ["locate", "Calculator"],
    ]

    for command in commands:
        args = parse_args([*command, "--format", "json"])
        assert args.format == "json"


def test_emit_json_produces_valid_deterministic_json(capsys) -> None:
    from context_forge.main import _emit_json

    _emit_json({"z": [], "a": {"value": 1}})

    output = capsys.readouterr().out
    assert json.loads(output) == {"a": {"value": 1}, "z": []}
    assert output == '{"a":{"value":1},"z":[]}\n'


def test_analyze_command_outputs_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {
            "root_path": Path("/tmp/project"),
            "files": [1, 2, 3],
            "symbols": [1, 2],
            "relationships": [1, 2, 3, 4],
            "analysis_status": "analyzed",
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "analyze", ".", "--format", "json"],
        ),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
        patch("context_forge.operational_logging.log_analysis_started"),
        patch("context_forge.operational_logging.log_analysis_completed"),
    ):
        analyzer.return_value.analyze.return_value = project
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "analysis_status": "analyzed",
        "files": 3,
        "relationships": 4,
        "repository": "/tmp/project",
        "symbols": 2,
    }


def test_status_command_outputs_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Freshness:
        is_fresh = True

    class Repository:
        def check_cache_freshness(self, repository_key, fingerprints):
            return Freshness()

    project = type(
        "Project",
        (),
        {
            "root_path": tmp_path.resolve(),
            "name": "sample-repo",
            "analysis_status": "analyzed",
            "project_type": "python",
            "files": [1],
            "symbols": [1, 2],
            "relationships": [],
            "errors": [],
        },
    )()

    metadata = type(
        "Metadata",
        (),
        {"cache_schema_version": 1, "analyzer_version": "0.1.0"},
    )()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "status", str(tmp_path), "--format", "json"],
        ),
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(Repository(), "sample-key", project, metadata),
        ),
        patch("context_forge.main.current_fingerprints", return_value={}),
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""

    payload = json.loads(captured.out)
    assert payload["repository"] == str(tmp_path.resolve())
    assert payload["cache_status"] == "fresh"
    assert payload["files"] == 1
    assert payload["symbols"] == 2
    assert payload["relationships"] == 0
    assert payload["analysis_errors"] == 0
    assert "cache_schema_version" not in payload
    assert "analyzer_version" not in payload


def test_cache_command_outputs_json_with_sorted_change_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Changes:
        added = ("z.py", "a.py")
        modified = ("d.py", "b.py")
        deleted = ("y.py", "c.py")

    class Freshness:
        is_fresh = False
        reason = "Files were modified"
        changes = Changes()

    class Repository:
        def check_cache_freshness(self, repository_key, fingerprints):
            return Freshness()

    project = type(
        "Project",
        (),
        {"root_path": tmp_path.resolve()},
    )()

    metadata = type(
        "Metadata",
        (),
        {"cache_schema_version": 1, "analyzer_version": "0.1.0"},
    )()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "cache", str(tmp_path), "--format", "json"],
        ),
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(Repository(), "sample-key", project, metadata),
        ),
        patch(
            "context_forge.main.current_fingerprints",
            return_value={"tracked.py": "hash"},
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""

    assert json.loads(captured.out) == {
        "added_paths": ["a.py", "z.py"],
        "cache_status": "stale",
        "deleted_paths": ["c.py", "y.py"],
        "freshness_reason": "Files were modified",
        "modified_paths": ["b.py", "d.py"],
        "repository": "sample-key",
        "tracked_files": 1,
    }


def test_inspect_command_outputs_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_obj = type("File", (), {"path": "auth/login.py"})()
    symbol_obj = type(
        "Symbol",
        (),
        {
            "file_id": 1,
            "start_line": 10,
            "end_line": 20,
            "name": "login",
            "qualified_name": "auth.login",
            "kind": "function",
        },
    )()
    relationship_type = type("RelationshipType", (), {"value": "imports"})()
    relationship = type(
        "Relationship",
        (),
        {
            "relationship_type": relationship_type,
            "source_id": "auth.login",
            "target_id": "hashlib",
        },
    )()

    project = type(
        "Project",
        (),
        {
            "root_path": tmp_path.resolve(),
            "files": [file_obj],
            "symbols": [symbol_obj],
            "relationships": [relationship],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "inspect", str(tmp_path), "--format", "json"],
        ),
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(None, "key", project, None),
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""

    assert json.loads(captured.out) == {
        "files": [{"path": "auth/login.py"}],
        "relationships": [
            {
                "source_id": "auth.login",
                "target_id": "hashlib",
                "type": "imports",
            }
        ],
        "repository": str(tmp_path.resolve()),
        "symbols": [
            {
                "end_line": 20,
                "kind": "function",
                "name": "login",
                "qualified_name": "auth.login",
                "start_line": 10,
            }
        ],
    }


def test_diagnostics_command_outputs_empty_errors_and_null_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_without_errors = type(
        "Project",
        (),
        {"root_path": tmp_path.resolve(), "errors": []},
    )()

    project_with_missing_details = type(
        "Project",
        (),
        {
            "root_path": tmp_path.resolve(),
            "errors": [
                type(
                    "Error",
                    (),
                    {
                        "severity": "error",
                        "message": "Unknown location",
                        "path": None,
                        "line": None,
                    },
                )()
            ],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "diagnostics",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(None, "key", project_without_errors, None),
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "errors": [],
        "repository": str(tmp_path.resolve()),
    }

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "diagnostics",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_project_analysis",
            return_value=(None, "key", project_with_missing_details, None),
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "errors": [
            {
                "line": None,
                "message": "Unknown location",
                "path": None,
                "severity": "error",
            }
        ],
        "repository": str(tmp_path.resolve()),
    }


def test_memory_search_json_reports_empty_results(
    tmp_path,
    monkeypatch,
    capsys,
):
    from context_forge.main import main

    monkeypatch.setattr(
        "context_forge.main.load_fresh_project",
        lambda path: (object(), None),
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.search",
        lambda self, query: [],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "context-forge",
            "memory",
            "search",
            "missing",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["query"] == "missing"
    assert payload["repository"] == str(tmp_path.resolve())
    assert payload["results"] == []


def test_memory_file_json_reports_missing_file(
    tmp_path,
    monkeypatch,
    capsys,
):
    from context_forge.main import main

    monkeypatch.setattr(
        "context_forge.main.load_fresh_project",
        lambda path: (object(), None),
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.get_file",
        lambda self, file_path: None,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "context-forge",
            "memory",
            "file",
            "missing.py",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["repository"] == str(tmp_path.resolve())
    assert payload["requested_path"] == "missing.py"
    assert payload["file"] is None


def test_memory_symbol_json_reports_no_matches(
    tmp_path,
    monkeypatch,
    capsys,
):
    from context_forge.main import main

    monkeypatch.setattr(
        "context_forge.main.load_fresh_project",
        lambda path: (type("Project", (), {"files": []})(), None),
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.find_symbols",
        lambda self, name: [],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "context-forge",
            "memory",
            "symbol",
            "missing_symbol",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["query"] == "missing_symbol"
    assert payload["repository"] == str(tmp_path.resolve())
    assert payload["matches"] == []


def test_memory_search_json_returns_ranked_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SearchResult(
        result_type=SearchResultType.SYMBOL,
        entity_id=UUID(int=1),
        name="hello",
        path="src/calculator.py",
        score=0.95,
        reason="Exact qualified symbol name match",
        qualified_name="Calculator.hello",
    )

    monkeypatch.setattr(
        "context_forge.main.load_fresh_project",
        lambda path: (object(), None),
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.search",
        lambda self, query: [result],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "context-forge",
            "memory",
            "search",
            "Calculator.hello",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload == {
        "query": "Calculator.hello",
        "repository": str(tmp_path.resolve()),
        "results": [
            {
                "name": "hello",
                "path": "src/calculator.py",
                "qualified_name": "Calculator.hello",
                "reason": "Exact qualified symbol name match",
                "score": 0.95,
                "type": "symbol",
            }
        ],
    }


def test_memory_file_json_returns_metadata_and_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "name": "main.py",
            "extension": ".py",
            "file_type": type(
                "FileType",
                (),
                {"value": "source"},
            )(),
            "size": 128,
        },
    )()

    symbol = type(
        "Symbol",
        (),
        {
            "name": "Calculator",
            "qualified_name": "Calculator",
            "kind": "class",
            "start_line": 1,
            "end_line": 10,
            "signature": "class Calculator",
        },
    )()

    project = type(
        "Project",
        (),
        {"files": [file]},
    )()

    monkeypatch.setattr(
        "context_forge.main.load_fresh_project",
        lambda path: (project, None),
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.get_file",
        lambda self, file_path: file,
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.find_symbols_in_file",
        lambda self, file_id: [symbol],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "context-forge",
            "memory",
            "file",
            "main.py",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload == {
        "file": {
            "extension": ".py",
            "name": "main.py",
            "path": "main.py",
            "size": 128,
            "symbols": [
                {
                    "end_line": 10,
                    "kind": "class",
                    "name": "Calculator",
                    "qualified_name": "Calculator",
                    "signature": "class Calculator",
                    "start_line": 1,
                }
            ],
            "type": "source",
        },
        "repository": str(tmp_path.resolve()),
        "requested_path": "main.py",
    }


def test_memory_symbol_json_returns_ordered_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_z = type(
        "File",
        (),
        {
            "id": UUID(int=2),
            "path": Path("src/zeta.py"),
        },
    )()

    file_a = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("src/alpha.py"),
        },
    )()

    symbol_z = type(
        "Symbol",
        (),
        {
            "file_id": file_z.id,
            "name": "run",
            "qualified_name": "Zeta.run",
            "kind": "function",
            "start_line": 5,
            "end_line": 8,
            "signature": "def run()",
        },
    )()

    symbol_a = type(
        "Symbol",
        (),
        {
            "file_id": file_a.id,
            "name": "run",
            "qualified_name": "Alpha.run",
            "kind": "function",
            "start_line": 2,
            "end_line": 4,
            "signature": "def run()",
        },
    )()

    project = type(
        "Project",
        (),
        {"files": [file_z, file_a]},
    )()

    monkeypatch.setattr(
        "context_forge.main.load_fresh_project",
        lambda path: (project, None),
    )
    monkeypatch.setattr(
        "context_forge.main.ProjectQuery.find_symbols",
        lambda self, name: [symbol_z, symbol_a],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "context-forge",
            "memory",
            "symbol",
            "run",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload == {
        "matches": [
            {
                "end_line": 4,
                "kind": "function",
                "name": "run",
                "path": "src/alpha.py",
                "qualified_name": "Alpha.run",
                "signature": "def run()",
                "start_line": 2,
            },
            {
                "end_line": 8,
                "kind": "function",
                "name": "run",
                "path": "src/zeta.py",
                "qualified_name": "Zeta.run",
                "signature": "def run()",
                "start_line": 5,
            },
        ],
        "query": "run",
        "repository": str(tmp_path.resolve()),
    }


def test_memory_references_json_reports_missing_symbol(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {"files": [], "symbols": []},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "references",
                "missing_symbol",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.find_symbols.return_value = []
        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["status"] == "not_found"
    assert payload["symbol"] == "missing_symbol"
    assert payload["matches"] == []
    assert payload["references"] == []


def test_memory_references_json_serializes_indexed_reference(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("src/main.py"),
        },
    )()

    symbol = type(
        "Symbol",
        (),
        {
            "id": UUID(int=2),
            "file_id": source_file.id,
            "name": "calculate",
            "qualified_name": "Calculator.calculate",
            "kind": "function",
            "start_line": 10,
            "end_line": 20,
        },
    )()

    relationship = type(
        "Relationship",
        (),
        {
            "id": UUID(int=3),
            "source_id": source_file.id,
            "target_id": symbol.id,
            "relationship_type": "references",
            "confidence": 0.9,
            "metadata": {
                "line": "12",
                "name": "calculate",
                "qualified_name": "Calculator.calculate",
            },
        },
    )()

    project = type(
        "Project",
        (),
        {"files": [source_file], "symbols": [symbol]},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "references",
                "calculate",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.find_symbols.return_value = [symbol]
        query_mock.return_value.get_incoming_relationships.return_value = [relationship]
        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["status"] == "ok"
    assert payload["matches"][0]["qualified_name"] == "Calculator.calculate"
    assert payload["references"] == [
        {
            "confidence": 0.9,
            "line": 12,
            "name": "calculate",
            "path": "src/main.py",
            "qualified_name": "Calculator.calculate",
            "relationship_type": "references",
        }
    ]


def test_memory_relationships_json_reports_empty_results(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("main.py"),
        },
    )()

    project = type(
        "Project",
        (),
        {"files": [file], "symbols": []},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "relationships",
                "main.py",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = file
        query_mock.return_value.get_relationships.return_value = []
        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["status"] == "ok"
    assert payload["entity_type"] == "file"
    assert payload["direction"] == "both"
    assert payload["relationships"] == []


def test_memory_relationships_json_reports_missing_entity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {"files": [], "symbols": []},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "relationships",
                "missing.py",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = None
        query_mock.return_value.find_symbols_by_qualified_name.return_value = []
        query_mock.return_value.find_symbols.return_value = []
        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["status"] == "not_found"
    assert payload["entity"] == "missing.py"
    assert payload["relationships"] == []


@pytest.mark.parametrize(
    ("error", "expected_stderr"),
    [
        (
            OSError("disk unavailable"),
            "Error: disk unavailable\n",
        ),
        (
            sqlite3.OperationalError("database is locked"),
            "Error: database is locked\n",
        ),
    ],
    ids=["filesystem-error", "database-error"],
)
def test_main_reports_operational_errors_without_traceback(
    error: Exception,
    expected_stderr: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "status", "."]),
        patch(
            "context_forge.main._dispatch_command",
            side_effect=error,
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == expected_stderr


def test_main_handles_keyboard_interrupt_during_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "status", "."]),
        patch(
            "context_forge.main._dispatch_command",
            side_effect=KeyboardInterrupt,
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 130

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "\n"


def test_parse_memory_dependencies_command() -> None:
    args = parse_args(
        [
            "memory",
            "dependencies",
            "src/main.py",
            "/tmp/project",
            "--direction",
            "dependents",
            "--format",
            "json",
        ]
    )

    assert args.command == "memory"
    assert args.memory_command == "dependencies"
    assert args.file_path == "src/main.py"
    assert args.path == Path("/tmp/project")
    assert args.direction == "dependents"
    assert args.format == "json"


@pytest.mark.parametrize(
    ("direction", "expected_dependencies", "expected_dependents"),
    [
        ("both", ["src/utils.py"], ["src/app.py"]),
        ("dependencies", ["src/utils.py"], []),
        ("dependents", [], ["src/app.py"]),
    ],
)
def test_memory_dependencies_outputs_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    direction: str,
    expected_dependencies: list[str],
    expected_dependents: list[str],
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("src/main.py"),
        },
    )()

    dependency = type(
        "File",
        (),
        {
            "id": UUID(int=2),
            "path": Path("src/utils.py"),
        },
    )()

    dependent = type(
        "File",
        (),
        {
            "id": UUID(int=3),
            "path": Path("src/app.py"),
        },
    )()

    project = type(
        "Project",
        (),
        {
            "files": [file, dependency, dependent],
            "symbols": [],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "dependencies",
                "src/main.py",
                str(tmp_path),
                "--direction",
                direction,
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = file
        query_mock.return_value.get_direct_dependencies.return_value = [dependency]
        query_mock.return_value.get_direct_dependents.return_value = [dependent]

        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload == {
        "repository": str(tmp_path.resolve()),
        "file": "src/main.py",
        "direction": direction,
        "status": "ok",
        "dependencies": expected_dependencies,
        "dependents": expected_dependents,
    }

    if direction in ("both", "dependencies"):
        query_mock.return_value.get_direct_dependencies.assert_called_once_with(file.id)
    else:
        query_mock.return_value.get_direct_dependencies.assert_not_called()

    if direction in ("both", "dependents"):
        query_mock.return_value.get_direct_dependents.assert_called_once_with(file.id)
    else:
        query_mock.return_value.get_direct_dependents.assert_not_called()


def test_memory_dependencies_reports_missing_file_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {
            "files": [],
            "symbols": [],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "dependencies",
                "missing.py",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = None
        main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload == {
        "repository": str(tmp_path.resolve()),
        "file": "missing.py",
        "direction": "both",
        "status": "not_found",
        "dependencies": [],
        "dependents": [],
    }

    query_mock.return_value.get_direct_dependencies.assert_not_called()
    query_mock.return_value.get_direct_dependents.assert_not_called()


def test_memory_dependencies_outputs_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file = type(
        "File",
        (),
        {
            "id": UUID(int=1),
            "path": Path("src/main.py"),
        },
    )()
    dependency = type(
        "File",
        (),
        {
            "id": UUID(int=2),
            "path": Path("src/utils.py"),
        },
    )()
    dependent = type(
        "File",
        (),
        {
            "id": UUID(int=3),
            "path": Path("src/app.py"),
        },
    )()
    project = type(
        "Project",
        (),
        {
            "files": [file, dependency, dependent],
            "symbols": [],
        },
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "dependencies",
                "src/main.py",
                str(tmp_path),
            ],
        ),
        patch(
            "context_forge.main.load_fresh_project",
            return_value=(project, None),
        ),
        patch("context_forge.main.ProjectQuery") as query_mock,
    ):
        query_mock.return_value.get_file.return_value = file
        query_mock.return_value.get_direct_dependencies.return_value = [dependency]
        query_mock.return_value.get_direct_dependents.return_value = [dependent]

        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert "File: src/main.py" in captured.out
    assert "Direct dependencies: 1" in captured.out
    assert "  src/utils.py" in captured.out
    assert "Direct dependents: 1" in captured.out
    assert "  src/app.py" in captured.out


def test_architecture_command_prints_text_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text("import pkg.lib\n", encoding="utf-8")
    (pkg / "lib.py").write_text("VALUE = 42\n", encoding="utf-8")

    # Analyze first
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Run architecture command
    with patch.object(sys, "argv", ["context-forge", "architecture", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"Repository: {tmp_path.resolve()}" in captured.out
    assert "Analysis status: analyzed" in captured.out
    assert "Packages:" in captured.out
    assert "pkg (3 modules)" in captured.out
    assert "Python modules:" in captured.out
    assert "pkg/app.py" in captured.out
    assert "imports -> pkg/lib.py" in captured.out
    assert "Resolved dependencies:" in captured.out
    assert "pkg/app.py -> pkg/lib.py" in captured.out
    assert "Dependency cycles:" in captured.out
    assert "None detected." in captured.out
    assert "Limitations:" in captured.out


def test_architecture_command_prints_json_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("X = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "architecture", str(tmp_path), "--format", "json"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["repository"] == str(tmp_path.resolve())
    assert payload["analysis"]["status"] == "analyzed"
    assert payload["counts"]["python_modules"] == 2
    assert payload["counts"]["packages"] == 1
    assert isinstance(payload["modules"]["items"], list)
    assert isinstance(payload["dependencies"]["items"], list)
    assert isinstance(payload["cycles"]["items"], list)
    assert isinstance(payload["limitations"], list)


def test_architecture_command_respects_limit_option(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for index in range(5):
        (tmp_path / f"mod_{index}.py").write_text(f"v = {index}\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "architecture", str(tmp_path), "--limit", "2"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "... showing 2 of 5 modules" in captured.out


def test_architecture_command_rejects_invalid_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path), "--limit", "0"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: Report limit must be a positive integer" in captured.err


def test_architecture_command_fails_on_uninitialized_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert (
        "No persisted analysis found; run 'context-forge analyze' first" in captured.err
    )


def test_architecture_command_fails_on_stale_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "file.py"
    source.write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Modify file to make cache stale
    source.write_text("x = 2\n", encoding="utf-8")

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Repository analysis is stale; run 'context-forge analyze" in captured.err


def test_architecture_command_handles_schema_v1_database_without_crashing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "app.py"
    source.write_text("import sys\n", encoding="utf-8")

    # Analyze project
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Drop imports table and set cache_schema_version = 1 to simulate pre-v0.11 database
    db_path = tmp_path / ".context_forge.db"
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS imports")
    conn.execute("UPDATE repository_cache SET cache_schema_version = 1")
    conn.commit()
    conn.close()

    # status must not crash with "no such table: imports"
    with patch.object(
        sys,
        "argv",
        ["context-forge", "status", str(tmp_path), "--format", "json"],
    ):
        main()
    status_captured = capsys.readouterr()
    assert status_captured.err == ""
    status_data = json.loads(status_captured.out)
    assert status_data["cache_status"] == "stale"
    assert "cache_schema_version" not in status_data
    assert "analyzer_version" not in status_data

    # cache command must also report stale with schema_version_mismatch
    with patch.object(
        sys,
        "argv",
        ["context-forge", "cache", str(tmp_path), "--format", "json"],
    ):
        main()
    cache_captured = capsys.readouterr()
    assert cache_captured.err == ""
    cache_data = json.loads(cache_captured.out)
    assert cache_data["cache_status"] == "stale"
    assert cache_data["freshness_reason"] == "schema_version_mismatch"

    # architecture must report stale analysis rather than crashing with "no such table: imports"
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    arch_captured = capsys.readouterr()
    assert "no such table: imports" not in arch_captured.err
    assert (
        "Repository analysis is stale; run 'context-forge analyze" in arch_captured.err
    )

    # Re-analyzing updates database schema cleanly
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Now architecture succeeds
    with patch.object(sys, "argv", ["context-forge", "architecture", str(tmp_path)]):
        main()
    final_captured = capsys.readouterr()
    assert final_captured.err == ""
    assert "Analysis status: analyzed" in final_captured.out


def test_architecture_command_prints_cycle_truncation_notices(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import c\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("import a\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "architecture", str(tmp_path), "--limit", "1"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Dependency cycles:" in captured.out
    assert "Cycle 1:" in captured.out
    assert "... showing 1 of 3 modules" in captured.out
    assert "... showing 1 of 3 dependencies" in captured.out


def test_impact_command_text_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (src_dir / "service.py").write_text(
        "import models\n\ndef get_user():\n    return models.User()\n",
        encoding="utf-8",
    )

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Query models.py
    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "src/models.py", str(tmp_path)],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"Repository: {tmp_path.resolve()}" in captured.out
    assert "Target query: src/models.py" in captured.out
    assert "Resolved target: [file] models.py (src/models.py)" in captured.out
    assert "Direction: both" in captured.out
    assert "Direct impact:" in captured.out
    assert "[incoming]" in captured.out
    assert "service.py [file]" in captured.out
    assert "Limitations:" in captured.out


def test_impact_command_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (src_dir / "service.py").write_text(
        "import models\n",
        encoding="utf-8",
    )

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "src/models.py", str(tmp_path), "--format", "json"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["status"] == "resolved"
    assert data["target"]["name"] == "models.py"
    assert data["target"]["target_type"] == "file"
    assert data["direction"] == "both"
    assert data["total"] >= 1
    assert data["truncated"] is False
    assert len(data["items"]) >= 1
    assert data["items"][0]["related_name"] == "service.py"
    assert "limitations" in data


def test_impact_command_missing_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Text format
    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "nonexistent_target", str(tmp_path)],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Status: Target not found." in captured.out
    assert "not found in repository" in captured.out

    # JSON format
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "impact",
            "nonexistent_target",
            str(tmp_path),
            "--format",
            "json",
        ],
    ):
        main()

    json_captured = capsys.readouterr()
    data = json.loads(json_captured.out)
    assert data["status"] == "not_found"
    assert data["target"] is None


def test_impact_command_ambiguous_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "mod_a.py").write_text("class Config:\n    pass\n", encoding="utf-8")
    (tmp_path / "mod_b.py").write_text("class Config:\n    pass\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Text format
    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "Config", str(tmp_path)],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Status: Ambiguous target." in captured.out
    assert "Candidates (2):" in captured.out
    assert "[class] Config" in captured.out

    # JSON format
    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "Config", str(tmp_path), "--format", "json"],
    ):
        main()

    json_captured = capsys.readouterr()
    data = json.loads(json_captured.out)
    assert data["status"] == "ambiguous"
    assert len(data["candidates"]) == 2


def test_impact_command_direction_and_type_filters(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import c\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Incoming only for b.py
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "impact",
            "b.py",
            str(tmp_path),
            "--direction",
            "incoming",
            "--format",
            "json",
        ],
    ):
        main()

    data = json.loads(capsys.readouterr().out)
    assert data["direction"] == "incoming"
    assert data["total"] == 1
    assert data["items"][0]["direction"] == "incoming"
    assert data["items"][0]["related_name"] == "a.py"

    # Outgoing only for b.py
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "impact",
            "b.py",
            str(tmp_path),
            "--direction",
            "outgoing",
            "--format",
            "json",
        ],
    ):
        main()

    data_out = json.loads(capsys.readouterr().out)
    assert data_out["direction"] == "outgoing"
    assert data_out["total"] == 1
    assert data_out["items"][0]["direction"] == "outgoing"
    assert data_out["items"][0]["related_name"] == "c.py"

    # Type filter: references (none exist, only imports)
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "impact",
            "b.py",
            str(tmp_path),
            "--type",
            "references",
            "--format",
            "json",
        ],
    ):
        main()

    data_ref = json.loads(capsys.readouterr().out)
    assert data_ref["total"] == 0
    assert data_ref["items"] == []


def test_impact_command_limit_truncation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "core.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "u1.py").write_text("import core\n", encoding="utf-8")
    (tmp_path / "u2.py").write_text("import core\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "core.py", str(tmp_path), "--limit", "1"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "... showing 1 of 2 items" in captured.out


def test_impact_command_stale_cache_aborts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target_file = tmp_path / "a.py"
    target_file.write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Modify file so cache is stale
    target_file.write_text("x = 2\n", encoding="utf-8")

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "impact", "a.py", str(tmp_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Repository analysis is stale" in captured.err


def test_impact_command_rejects_empty_target_or_invalid_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "impact", "", str(tmp_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Target cannot be empty" in captured.err

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "impact", "a.py", str(tmp_path), "--limit", "0"],
        ),
        pytest.raises(SystemExit) as exc_info2,
    ):
        main()

    assert exc_info2.value.code == 1
    captured2 = capsys.readouterr()
    assert "positive integer" in captured2.err


def test_impact_command_transitive_depth_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import a\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("import b\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "impact", "a.py", str(tmp_path), "--depth", "2"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Traversal depth: 2 (reached: 2)" in captured.out
    assert "Impacted components: 2 (1 direct, 1 indirect)" in captured.out
    assert "Direct impact:" in captured.out
    assert "[incoming] imports: b.py [file]" in captured.out
    assert "Indirect impact:" in captured.out
    assert "[depth 2] [incoming] imports: c.py [file]" in captured.out
    assert "Path: a.py -[imports]-> b.py -[imports]-> c.py" in captured.out


def test_impact_command_transitive_depth_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import a\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("import b\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Test with --max-depth alias in json mode
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "impact",
            "a.py",
            str(tmp_path),
            "--max-depth",
            "2",
            "--format",
            "json",
        ],
    ):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "resolved"
    assert data["max_depth"] == 2
    assert data["depth_reached"] == 2
    assert data["direct_count"] == 1
    assert data["indirect_count"] == 1
    assert data["total"] == 2
    assert len(data["items"]) == 2

    direct_item = data["items"][0]
    assert direct_item["related_name"] == "b.py"
    assert direct_item["depth"] == 1
    assert direct_item["classification"] == "direct"
    assert len(direct_item["path"]) == 1

    indirect_item = data["items"][1]
    assert indirect_item["related_name"] == "c.py"
    assert indirect_item["depth"] == 2
    assert indirect_item["classification"] == "indirect"
    assert len(indirect_item["path"]) == 2
    assert indirect_item["path"][0]["to_name"] == "b.py"
    assert indirect_item["path"][1]["to_name"] == "c.py"


def test_impact_command_rejects_invalid_depth(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "impact", "a.py", str(tmp_path), "--depth", "0"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "positive integer" in capsys.readouterr().err


def test_health_command_text_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("def hello():\n    return 42\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("import a\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(sys, "argv", ["context-forge", "health", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"Repository: {tmp_path.resolve()}" in captured.out
    assert "Analysis state:" in captured.out
    assert "Status: analyzed" in captured.out
    assert "Cache status: fresh" in captured.out
    assert "Inventory:" in captured.out
    assert "Files: 2" in captured.out
    assert "Python modules: 2" in captured.out
    assert "Findings summary:" in captured.out
    assert "Limitations:" in captured.out
    assert "Cache schema version" not in captured.out
    assert "Analyzer version" not in captured.out


def test_health_command_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "health", str(tmp_path), "--format", "json"],
    ):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["schema_version"] == 1
    assert data["repository"] == tmp_path.resolve().as_posix()
    assert data["analysis"]["status"] == "analyzed"
    assert data["analysis"]["error_count"] == 0
    assert data["cache"]["status"] == "fresh"
    assert "cache_schema_version" not in data["cache"]
    assert "analyzer_version" not in data["cache"]
    assert data["inventory"]["files"] == 1
    assert isinstance(data["inventory"]["files"], int)
    assert data["findings"]["summary"]["total_findings"] == 0
    assert isinstance(data["limitations"], list)


def test_health_command_stale_cache_does_not_abort(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target_file = tmp_path / "a.py"
    target_file.write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Modify file so cache is stale
    target_file.write_text("x = 2\n", encoding="utf-8")

    # health should succeed and report stale cache, rather than aborting
    with patch.object(
        sys,
        "argv",
        ["context-forge", "health", str(tmp_path)],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Cache status: stale" in captured.out
    assert "Cached analysis is stale" in captured.out


def test_health_command_unanalyzed_repository_aborts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "health", str(tmp_path)]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "No persisted analysis found" in capsys.readouterr().err


def test_health_command_rejects_invalid_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "health", str(tmp_path), "--limit", "0"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "positive integer" in capsys.readouterr().err


def test_health_command_empty_analyzed_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Analyze an empty directory
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "health", str(tmp_path), "--format", "json"],
    ):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["analysis"]["status"] == "analyzed"
    assert data["inventory"]["files"] == 0
    assert data["inventory"]["symbols"] == 0
    assert data["findings"]["summary"]["total_findings"] == 0


def test_cf_entry_point_displays_help(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["cf", "--help"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage: context-forge" in captured.out
    assert "architecture" in captured.out
    assert "impact" in captured.out
    assert "health" in captured.out
    assert captured.err == ""


def test_cf_entry_point_dispatches_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch.object(sys, "argv", ["cf", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    with patch.object(sys, "argv", ["cf", "status", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Analysis status: analyzed" in captured.out


@pytest.mark.parametrize(
    "argv",
    [
        ["architecture"],
        ["health"],
        ["impact", "a.py"],
        ["memory", "dependencies", "a.py"],
        ["memory", "relationships", "a.py"],
        ["status"],
        ["diagnostics"],
        ["inspect"],
        ["cache"],
    ],
)
def test_unanalyzed_repository_read_only_invariance(
    tmp_path: Path,
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_file = tmp_path / ".context_forge.db"
    assert not db_file.exists()

    with (
        patch.object(sys, "argv", ["context-forge", *argv, str(tmp_path)]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "No persisted analysis found; run 'context-forge analyze' first" in captured.err
    )
    # Invariant: running read-only query commands must not create .context_forge.db
    assert not db_file.exists()
    assert list(tmp_path.iterdir()) == []


def test_unanalyzed_directory_missing_db_avoids_database_connection(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / ".context_forge.db"
    assert not db_file.exists()

    with patch("context_forge.main.Database") as database_mock:
        with pytest.raises(
            ValueError,
            match="No persisted analysis found; run 'context-forge analyze' first",
        ):
            load_project_analysis(tmp_path)

        database_mock.assert_not_called()


@pytest.mark.parametrize(
    ("argv", "must_abort"),
    [
        (["architecture"], True),
        (["impact", "a.py"], True),
        (["memory", "dependencies", "a.py"], True),
        (["memory", "relationships", "a.py"], True),
        (["health"], False),
        (["status"], False),
        (["cache"], False),
        (["diagnostics"], False),
        (["inspect"], False),
    ],
)
def test_freshness_policy_matrix(
    tmp_path: Path,
    argv: list[str],
    must_abort: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target_file = tmp_path / "a.py"
    target_file.write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Make analysis stale by modifying file
    target_file.write_text("x = 2\n", encoding="utf-8")

    if must_abort:
        with (
            patch.object(sys, "argv", ["context-forge", *argv, str(tmp_path)]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert (
            "Repository analysis is stale; run 'context-forge analyze" in captured.err
        )
    else:
        with patch.object(sys, "argv", ["context-forge", *argv, str(tmp_path)]):
            main()

        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out != ""


@pytest.mark.parametrize(
    "argv",
    [
        ["architecture", "--format", "json"],
        ["health", "--format", "json"],
        ["impact", "a.py", "--format", "json"],
        ["memory", "dependencies", "a.py", "--format", "json"],
        ["memory", "relationships", "a.py", "--format", "json"],
        ["status", "--format", "json"],
        ["cache", "--format", "json"],
        ["diagnostics", "--format", "json"],
        ["inspect", "--format", "json"],
    ],
)
def test_deterministic_json_output_across_queries(
    tmp_path: Path,
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("import b\ndef fn(): return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def helper(): return 2\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # First invocation
    with patch.object(sys, "argv", ["context-forge", *argv, str(tmp_path)]):
        main()
    first_out = capsys.readouterr().out

    # Second invocation
    with patch.object(sys, "argv", ["context-forge", *argv, str(tmp_path)]):
        main()
    second_out = capsys.readouterr().out

    assert first_out == second_out
    # Must be valid json
    parsed = json.loads(first_out)
    assert isinstance(parsed, dict)


def test_output_channel_separation_on_handled_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # 1. Invalid limit error
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path), "--limit", "0"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: Report limit must be a positive integer\n"

    # 2. Non-existent path error
    missing_dir = tmp_path / "non_existent"
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "health", str(missing_dir)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: Project path does not exist:")
    assert "Traceback" not in captured.err


def test_cli_output_omits_internal_version_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "mod.py").write_text("x = 42\n", encoding="utf-8")
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Text output checks
    for cmd in (["status"], ["cache"], ["health"]):
        with patch.object(sys, "argv", ["context-forge", *cmd, str(tmp_path)]):
            main()
        captured = capsys.readouterr()
        assert "Cache schema version" not in captured.out
        assert "Analyzer version" not in captured.out

    # JSON output checks
    for cmd in (["status"], ["cache"]):
        with patch.object(
            sys, "argv", ["context-forge", *cmd, str(tmp_path), "--format", "json"]
        ):
            main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "cache_schema_version" not in data
        assert "analyzer_version" not in data

    with patch.object(
        sys, "argv", ["context-forge", "health", str(tmp_path), "--format", "json"]
    ):
        main()
    captured = capsys.readouterr()
    health_data = json.loads(captured.out)
    assert "cache_schema_version" not in health_data["cache"]
    assert "analyzer_version" not in health_data["cache"]


def test_internal_cache_version_mismatch_preserves_freshness_invalidation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "mod.py").write_text("x = 42\n", encoding="utf-8")
    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    db_path = tmp_path / ".context_forge.db"

    # 1. Test analyzer version mismatch
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE repository_cache SET analyzer_version = 'old_analyzer'")
    conn.commit()
    conn.close()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "cache", str(tmp_path), "--format", "json"],
    ):
        main()
    cache_data = json.loads(capsys.readouterr().out)
    assert cache_data["cache_status"] == "stale"
    assert cache_data["freshness_reason"] == "analyzer_version_mismatch"

    # 2. Test schema version mismatch
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE repository_cache SET cache_schema_version = 0")
    conn.commit()
    conn.close()

    with patch.object(
        sys,
        "argv",
        ["context-forge", "cache", str(tmp_path), "--format", "json"],
    ):
        main()
    cache_data = json.loads(capsys.readouterr().out)
    assert cache_data["cache_status"] == "stale"
    assert cache_data["freshness_reason"] == "schema_version_mismatch"


def test_cli_json_mode_reports_blocked_operation_on_missing_analysis(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path), "--format", "json"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error_payload = json.loads(captured.err)
    assert error_payload["status"] == "blocked"
    assert error_payload["is_success"] is False
    assert (
        "No persisted analysis found; run 'context-forge analyze' first"
        in error_payload["message"]
    )
    assert error_payload["summary"]["blockers"] == 1
    assert error_payload["diagnostics"][0]["code"] == "MISSING_ANALYSIS"
    assert error_payload["diagnostics"][0]["severity"] == "blocker"


def test_cli_json_mode_reports_blocked_operation_on_stale_analysis(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_file = tmp_path / "mod.py"
    source_file.write_text("x = 1\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "analyze", str(tmp_path)]):
        main()
    capsys.readouterr()

    # Make cache stale
    source_file.write_text("x = 2\n", encoding="utf-8")

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "architecture", str(tmp_path), "--format", "json"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error_payload = json.loads(captured.err)
    assert error_payload["status"] == "blocked"
    assert error_payload["is_success"] is False
    assert "Repository analysis is stale" in error_payload["message"]
    assert error_payload["summary"]["blockers"] == 1
    assert error_payload["diagnostics"][0]["code"] == "STALE_ANALYSIS"
    assert error_payload["diagnostics"][0]["severity"] == "blocker"


def test_cli_json_mode_reports_operational_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "architecture",
                str(tmp_path),
                "--limit",
                "0",
                "--format",
                "json",
            ],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error_payload = json.loads(captured.err)
    assert error_payload["status"] == "failed"
    assert error_payload["is_success"] is False
    assert error_payload["message"] == "Report limit must be a positive integer"
    assert error_payload["summary"]["errors"] == 1
    assert error_payload["diagnostics"][0]["severity"] == "error"


def test_cli_text_mode_regression_preserves_stderr_format(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "architecture",
                str(tmp_path),
                "--limit",
                "0",
            ],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Error: Report limit must be a positive integer\n"


def test_preflight_command_text_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "app.py").write_text("def fn(): pass\n", encoding="utf-8")

    with patch.object(sys, "argv", ["context-forge", "preflight", str(tmp_path)]):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"Repository: {tmp_path.resolve()}" in captured.out
    assert "Readiness: READY" in captured.out
    assert "Repository status:" in captured.out
    assert "Configuration:" in captured.out
    assert "Inventory:" in captured.out
    assert "Analysis readiness:" in captured.out


def test_preflight_command_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    with patch.object(
        sys,
        "argv",
        ["context-forge", "preflight", str(tmp_path), "--format", "json"],
    ):
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["repository"] == tmp_path.resolve().as_posix()
    assert payload["readiness"] in ("ready", "ready_with_limitations")
    assert payload["outcome"]["is_success"] is True
    assert payload["inventory"]["files"] == 1
    assert payload["configuration"]["status"] == "default"


def test_preflight_command_blocked_on_nonexistent_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_dir = tmp_path / "nonexistent_repo"

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "preflight", str(missing_dir)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Readiness: BLOCKED" in captured.out
    assert "REPOSITORY_NOT_FOUND" in captured.out


def test_preflight_command_json_blocked_exits_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_dir = tmp_path / "nonexistent_repo"

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "preflight", str(missing_dir), "--format", "json"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["readiness"] == "blocked"
    assert payload["outcome"]["is_success"] is False
    assert payload["outcome"]["status"] == "blocked"


def test_preflight_command_read_only_invariance(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_file = tmp_path / ".context_forge.db"
    assert not db_file.exists()

    with patch.object(sys, "argv", ["context-forge", "preflight", str(tmp_path)]):
        main()

    capsys.readouterr()
    assert not db_file.exists(), "Preflight must not create .context_forge.db"


def test_parse_locate_command() -> None:
    from context_forge.main import parse_args

    args = parse_args(["locate", "Calculator"])
    assert args.command == "locate"
    assert args.symbol_name == "Calculator"
    assert args.path == Path(".")
    assert args.file_path is None
    assert args.symbol_type is None
    assert args.excerpt is False
    assert args.max_lines == 50

    args = parse_args(
        [
            "locate",
            "calculate",
            "/tmp/project",
            "--file",
            "src/calc.py",
            "--type",
            "method",
            "--excerpt",
            "--max-lines",
            "20",
        ]
    )
    assert args.command == "locate"
    assert args.symbol_name == "calculate"
    assert args.path == Path("/tmp/project")
    assert args.file_path == "src/calc.py"
    assert args.symbol_type == "method"
    assert args.excerpt is True
    assert args.max_lines == 20


def test_locate_command_unique_match_text_and_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calc_path = tmp_path / "src" / "calc.py"
    calc_path.parent.mkdir(parents=True, exist_ok=True)
    calc_path.write_text("class Calculator:\n    pass\n", encoding="utf-8")

    file_id = UUID(int=1)
    file_one = type("File", (), {"id": file_id, "path": Path("src/calc.py")})()
    symbol_one = type(
        "Symbol",
        (),
        {
            "id": UUID(int=10),
            "file_id": file_id,
            "name": "Calculator",
            "qualified_name": "calc.Calculator",
            "kind": "class",
            "start_line": 1,
            "end_line": 2,
            "signature": "class Calculator:",
        },
    )()

    project = type(
        "Project",
        (),
        {
            "id": UUID(int=100),
            "root_path": tmp_path.resolve(),
            "files": [file_one],
            "symbols": [symbol_one],
            "relationships": [],
        },
    )()
    metadata = type("Metadata", (), {})()

    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(
            sys, "argv", ["context-forge", "locate", "Calculator", str(tmp_path)]
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert "Status: RESOLVED" in captured.out
    assert "Target: [class] calc.Calculator" in captured.out
    assert "File: src/calc.py" in captured.out
    assert "Lines: 1-2" in captured.out

    # JSON output
    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "locate",
                "Calculator",
                str(tmp_path),
                "--format",
                "json",
            ],
        ),
    ):
        main()

    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert data["schema_version"] == 1
    assert data["status"] == "resolved"
    assert data["target"]["name"] == "Calculator"
    assert data["target"]["path"] == "src/calc.py"
    assert data["outcome"]["is_success"] is True


def test_locate_command_with_excerpt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calc_path = tmp_path / "src" / "calc.py"
    calc_path.parent.mkdir(parents=True, exist_ok=True)
    calc_path.write_text(
        "class Calculator:\n    def add(self, x, y):\n        return x + y\n",
        encoding="utf-8",
    )

    file_id = UUID(int=1)
    file_one = type("File", (), {"id": file_id, "path": Path("src/calc.py")})()
    symbol_one = type(
        "Symbol",
        (),
        {
            "id": UUID(int=10),
            "file_id": file_id,
            "name": "Calculator",
            "qualified_name": "calc.Calculator",
            "kind": "class",
            "start_line": 1,
            "end_line": 3,
            "signature": "class Calculator:",
        },
    )()

    project = type(
        "Project",
        (),
        {
            "id": UUID(int=100),
            "root_path": tmp_path.resolve(),
            "files": [file_one],
            "symbols": [symbol_one],
            "relationships": [],
        },
    )()
    metadata = type("Metadata", (), {})()

    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(
            sys,
            "argv",
            ["context-forge", "locate", "Calculator", str(tmp_path), "--excerpt"],
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert "Source excerpt (src/calc.py:1-3):" in captured.out
    assert "class Calculator:" in captured.out
    assert "def add(self, x, y):" in captured.out

    # JSON format with excerpt
    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "locate",
                "Calculator",
                str(tmp_path),
                "--excerpt",
                "--format",
                "json",
            ],
        ),
    ):
        main()

    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert data["excerpt"] is not None
    assert data["excerpt"]["is_success"] is True
    assert "class Calculator:" in data["excerpt"]["content"]


def test_locate_command_ambiguous_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_1 = type("File", (), {"id": UUID(int=1), "path": Path("src/one.py")})()
    file_2 = type("File", (), {"id": UUID(int=2), "path": Path("src/two.py")})()
    sym_1 = type(
        "Symbol",
        (),
        {
            "id": UUID(int=10),
            "file_id": file_1.id,
            "name": "render",
            "qualified_name": "one.render",
            "kind": "function",
            "start_line": 1,
            "end_line": 2,
            "signature": "def render():",
        },
    )()
    sym_2 = type(
        "Symbol",
        (),
        {
            "id": UUID(int=20),
            "file_id": file_2.id,
            "name": "render",
            "qualified_name": "two.render",
            "kind": "function",
            "start_line": 1,
            "end_line": 2,
            "signature": "def render():",
        },
    )()
    project = type(
        "Project",
        (),
        {
            "id": UUID(int=100),
            "root_path": tmp_path.resolve(),
            "files": [file_1, file_2],
            "symbols": [sym_1, sym_2],
            "relationships": [],
        },
    )()
    metadata = type("Metadata", (), {})()

    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(sys, "argv", ["context-forge", "locate", "render", str(tmp_path)]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Status: AMBIGUOUS" in captured.out
    assert "Candidates:" in captured.out
    assert "one.render" in captured.out
    assert "two.render" in captured.out


def test_locate_command_not_found_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = type(
        "Project",
        (),
        {
            "id": UUID(int=100),
            "root_path": tmp_path.resolve(),
            "files": [],
            "symbols": [],
            "relationships": [],
        },
    )()
    metadata = type("Metadata", (), {})()

    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(
            sys, "argv", ["context-forge", "locate", "UnknownSymbol", str(tmp_path)]
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Status: NOT_FOUND" in captured.out
    assert "Symbol 'UnknownSymbol' not found" in captured.out


def test_memory_symbol_with_filters_and_excerpt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    view_path = tmp_path / "src" / "view.py"
    view_path.parent.mkdir(parents=True, exist_ok=True)
    view_path.write_text(
        "class View:\n    def display(self):\n        pass\n", encoding="utf-8"
    )

    file_id = UUID(int=1)
    file_one = type("File", (), {"id": file_id, "path": Path("src/view.py")})()
    symbol_one = type(
        "Symbol",
        (),
        {
            "id": UUID(int=10),
            "file_id": file_id,
            "name": "display",
            "qualified_name": "view.View.display",
            "kind": "method",
            "start_line": 2,
            "end_line": 3,
            "signature": "def display(self):",
        },
    )()

    project = type(
        "Project",
        (),
        {
            "id": UUID(int=100),
            "root_path": tmp_path.resolve(),
            "files": [file_one],
            "symbols": [symbol_one],
            "relationships": [],
        },
    )()
    metadata = type("Metadata", (), {})()

    with (
        patch(
            "context_forge.main.load_fresh_project", return_value=(project, metadata)
        ),
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "memory",
                "symbol",
                "display",
                str(tmp_path),
                "--file",
                "src/view.py",
                "--type",
                "method",
                "--excerpt",
            ],
        ),
    ):
        main()

    captured = capsys.readouterr()
    assert "Symbol: display" in captured.out
    assert "- [method] view.View.display" in captured.out
    assert "Path: src/view.py" in captured.out
    assert "Source excerpt (lines 2-3):" in captured.out
    assert "def display(self):" in captured.out
