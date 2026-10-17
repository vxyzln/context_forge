import json
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
