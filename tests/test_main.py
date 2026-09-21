import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.config import (
    ProjectConfiguration,
    ProjectGenerationConfiguration,
    ProjectProviderConfiguration,
)
from context_forge.main import (
    build_provider_config,
    load_project_analysis,
    main,
    parse_args,
    resolve_project_path,
    run_status,
)
from context_forge.provider import ProviderConfig


def test_main_reports_provider_error_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "."]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.side_effect = RuntimeError(
            "Ollama provider request timed out after 60 seconds"
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Ollama provider request timed out after 60 seconds\n"


def test_main_prints_generation_response(
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = type(
        "Response",
        (),
        {"content": "The scrolling behaviour is controlled by scroll.js."},
    )()

    with (
        patch.object(sys, "argv", ["context-forge", "."]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.return_value.generate.return_value = response

        main()

    captured = capsys.readouterr()

    assert captured.out == "\nThe scrolling behaviour is controlled by scroll.js.\n"
    assert captured.err == ""


def test_main_uses_default_provider_configuration() -> None:
    expected_config = ProviderConfig(
        provider="ollama",
        model="qwen2.5-coder:7b",
        temperature=0.0,
        max_tokens=None,
        base_url="http://localhost:11434",
    )

    with (
        patch.object(sys, "argv", ["context-forge", "."]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.return_value.generate.return_value = type(
            "Response",
            (),
            {"content": "Done."},
        )()

        main()

    build_service.assert_called_once_with(expected_config)

    build_service.return_value.generate.assert_called_once()

    call = build_service.return_value.generate.call_args

    assert call.kwargs["task"] == "Fix scrolling"
    assert call.kwargs["config"] == expected_config


def test_main_uses_custom_provider_configuration() -> None:
    expected_config = ProviderConfig(
        provider="deterministic",
        model="custom-model",
        temperature=0.7,
        max_tokens=512,
        base_url="http://example.test:11434",
    )

    argv = [
        "context-forge",
        ".",
        "--provider",
        "deterministic",
        "--model",
        "custom-model",
        "--temperature",
        "0.7",
        "--max-tokens",
        "512",
        "--base-url",
        "http://example.test:11434",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.return_value.generate.return_value = type(
            "Response",
            (),
            {"content": "Done."},
        )()

        main()

    build_service.assert_called_once_with(expected_config)

    build_service.return_value.generate.assert_called_once()

    call = build_service.return_value.generate.call_args

    assert call.kwargs["task"] == "Fix scrolling"
    assert call.kwargs["config"] == expected_config


def test_main_passes_same_configuration_to_service_and_generation() -> None:
    with (
        patch.object(sys, "argv", ["context-forge", "."]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.return_value.generate.return_value = type(
            "Response",
            (),
            {"content": "Done."},
        )()

        main()

    service_config = build_service.call_args.args[0]
    generation_config = build_service.return_value.generate.call_args.kwargs["config"]

    assert generation_config is service_config


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
            ["context-forge", str(missing_path)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        f"Error: Project path does not exist: {missing_path.resolve()}\n"
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
            ["context-forge", str(project_file)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        f"Error: Project path is not a directory: {project_file.resolve()}\n"
    )


def test_build_provider_config_uses_built_in_defaults() -> None:
    args = argparse.Namespace(
        provider=None,
        model=None,
        temperature=None,
        max_tokens=None,
        base_url=None,
    )

    config = build_provider_config(args, Path.cwd())

    assert config == ProviderConfig(
        provider="ollama",
        model="qwen2.5-coder:7b",
        temperature=0.0,
        max_tokens=None,
        base_url="http://localhost:11434",
    )


def test_build_provider_config_uses_project_over_global(
    tmp_path: Path,
) -> None:
    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            model="project-model",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
        ),
    )

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

    args = argparse.Namespace(
        provider=None,
        model=None,
        temperature=None,
        max_tokens=None,
        base_url=None,
    )

    with (
        patch(
            "context_forge.main.load_global_configuration",
            return_value=global_config,
        ),
        patch(
            "context_forge.main.load_project_configuration",
            return_value=project_config,
        ),
    ):
        config = build_provider_config(args, tmp_path)

    assert config == ProviderConfig(
        provider="deterministic",
        model="project-model",
        temperature=0.2,
        max_tokens=1024,
        base_url="http://global",
    )


def test_build_provider_config_cli_overrides_project_and_global(
    tmp_path: Path,
) -> None:
    project_config = ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="ollama",
            model="project-model",
            base_url="http://project",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
            max_tokens=512,
        ),
    )

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

    args = argparse.Namespace(
        provider="deterministic",
        model="cli-model",
        temperature=1.0,
        max_tokens=2048,
        base_url="http://cli",
    )

    with (
        patch(
            "context_forge.main.load_global_configuration",
            return_value=global_config,
        ),
        patch(
            "context_forge.main.load_project_configuration",
            return_value=project_config,
        ),
    ):
        config = build_provider_config(args, tmp_path)

    assert config == ProviderConfig(
        provider="deterministic",
        model="cli-model",
        temperature=1.0,
        max_tokens=2048,
        base_url="http://cli",
    )


def test_build_provider_config_resolves_complete_configuration_stack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    global_config_path = tmp_path / "global.toml"
    global_config_path.write_text(
        """
[provider]
provider = "deterministic"
model = "global-model"
base_url = "http://global"

[generation]
temperature = 0.7
max_tokens = 1024
""",
        encoding="utf-8",
    )

    project_root = tmp_path / "project"
    project_root.mkdir()

    (project_root / ".contextforge.toml").write_text(
        """
[provider]
model = "project-model"

[generation]
max_tokens = 2048
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: global_config_path,
    )

    args = argparse.Namespace(
        provider=None,
        model=None,
        temperature=None,
        max_tokens=None,
        base_url=None,
    )

    result = build_provider_config(args, project_root)

    assert result == ProviderConfig(
        provider="deterministic",
        model="project-model",
        temperature=0.7,
        max_tokens=2048,
        base_url="http://global",
    )


def test_build_provider_config_cli_values_override_all_configuration_layers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    global_config_path = tmp_path / "global.toml"
    global_config_path.write_text(
        """
[provider]
provider = "deterministic"
model = "global-model"
base_url = "http://global"

[generation]
temperature = 0.3
max_tokens = 512
""",
        encoding="utf-8",
    )

    project_root = tmp_path / "project"
    project_root.mkdir()

    (project_root / ".contextforge.toml").write_text(
        """
[provider]
model = "project-model"
base_url = "http://project"

[generation]
temperature = 0.7
max_tokens = 1024
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: global_config_path,
    )

    args = argparse.Namespace(
        provider="ollama",
        model="cli-model",
        temperature=1.2,
        max_tokens=4096,
        base_url="http://cli",
    )

    result = build_provider_config(args, project_root)

    assert result == ProviderConfig(
        provider="ollama",
        model="cli-model",
        temperature=1.2,
        max_tokens=4096,
        base_url="http://cli",
    )


def test_main_logs_generation_lifecycle(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    response = type(
        "Response",
        (),
        {"content": "Done."},
    )()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", str(project)],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch(
            "context_forge.main.build_generation_service",
        ) as build_service,
        patch(
            "context_forge.main.log_generation_started",
        ) as log_started,
        patch(
            "context_forge.main.log_generation_completed",
        ) as log_completed,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.return_value.generate.return_value = response

        main()

    log_started.assert_called_once_with(
        project_path=project.resolve(),
        provider="ollama",
        model="qwen2.5-coder:7b",
    )

    log_completed.assert_called_once()

    completed_call = log_completed.call_args.kwargs

    assert completed_call["project_path"] == project.resolve()
    assert completed_call["provider"] == "ollama"
    assert completed_call["model"] == "qwen2.5-coder:7b"
    assert completed_call["duration_seconds"] >= 0


def test_main_logs_generation_failure_without_task(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    error = RuntimeError("Ollama provider request timed out")

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", str(project)],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch(
            "context_forge.main.build_generation_service",
        ) as build_service,
        patch(
            "context_forge.main.log_generation_started",
        ),
        patch(
            "context_forge.main.log_generation_completed",
        ) as log_completed,
        patch(
            "context_forge.main.log_generation_failed",
        ) as log_failed,
        patch("builtins.input", return_value="Fix scrolling"),
    ):
        build_service.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    log_completed.assert_not_called()
    log_failed.assert_called_once()

    failed_call = log_failed.call_args.kwargs

    assert failed_call["project_path"] == project.resolve()
    assert failed_call["provider"] == "ollama"
    assert failed_call["model"] == "qwen2.5-coder:7b"
    assert failed_call["duration_seconds"] >= 0
    assert failed_call["error"] is error

    # The user's task must never be passed to the logger.
    assert "Fix scrolling" not in str(log_failed.call_args)


def test_main_without_project_path_prints_help_without_analyzing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge"]),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
        patch("builtins.input") as input_mock,
        patch("context_forge.main.build_generation_service") as build_service,
    ):
        main()

    captured = capsys.readouterr()

    assert "usage: context-forge" in captured.out
    assert "Generate context-forge responses for software projects." in captured.out
    assert captured.err == ""

    analyzer.assert_not_called()
    input_mock.assert_not_called()
    build_service.assert_not_called()


def test_main_runs_complete_python_project_workflow(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = """
def authenticate(username, password):
    return username == "admin" and password == "secret"
"""

    source_file = tmp_path / "auth.py"
    source_file.write_text(source, encoding="utf-8")

    argv = [
        "context-forge",
        str(tmp_path),
        "--provider",
        "deterministic",
        "--model",
        "deterministic-test",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("builtins.input", return_value="Explain the authenticate function"),
    ):
        main()

    captured = capsys.readouterr()

    assert captured.err == ""
    assert captured.out
    assert "Explain the authenticate function" in captured.out
    assert "Context received:" in captured.out


def test_main_reports_generation_provider_failure_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError("Ollama provider request timed out after 60 seconds")

    with (
        patch.object(sys, "argv", ["context-forge", str(tmp_path)]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.log_generation_started"),
        patch("context_forge.main.log_generation_completed") as log_completed,
        patch("context_forge.main.log_generation_failed") as log_failed,
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="Fix scrolling"),
        pytest.raises(SystemExit) as exc_info,
    ):
        build_service.return_value.generate.side_effect = error
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        "Error: Ollama provider request timed out after 60 seconds\n"
    )

    log_completed.assert_not_called()
    log_failed.assert_called_once()

    failed_call = log_failed.call_args.kwargs

    assert failed_call["project_path"] == tmp_path.resolve()
    assert failed_call["provider"] == "ollama"
    assert failed_call["model"] == "qwen2.5-coder:7b"
    assert failed_call["duration_seconds"] >= 0
    assert failed_call["error"] is error
    assert "Fix scrolling" not in str(log_failed.call_args)


def test_main_handles_keyboard_interrupt_during_task_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = [
        "context-forge",
        str(tmp_path),
        "--provider",
        "deterministic",
        "--model",
        "deterministic-test",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("builtins.input", side_effect=KeyboardInterrupt),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    captured = capsys.readouterr()

    assert exc_info.value.code == 130
    assert captured.out == ""
    assert "Traceback" not in captured.err


def test_main_handles_eof_during_task_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = [
        "context-forge",
        str(tmp_path),
        "--provider",
        "deterministic",
        "--model",
        "deterministic-test",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("builtins.input", side_effect=EOFError),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    captured = capsys.readouterr()

    assert exc_info.value.code == 1
    assert captured.out == ""
    assert "Error: Task input ended unexpectedly" in captured.err
    assert "Traceback" not in captured.err


def test_main_reports_analysis_failure_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError("repository analysis failed")

    with (
        patch.object(sys, "argv", ["context-forge", str(tmp_path)]),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
        patch("builtins.input") as input_mock,
        patch("context_forge.main.build_generation_service") as build_service,
    ):
        analyzer.return_value.analyze.side_effect = error

        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: repository analysis failed\n"

    input_mock.assert_not_called()
    build_service.assert_not_called()


def test_main_reports_configuration_failure_without_generation_failure_log(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = ValueError("invalid provider configuration")

    with (
        patch.object(sys, "argv", ["context-forge", str(tmp_path)]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_provider_config", side_effect=error),
        patch("context_forge.main.log_generation_failed") as log_failed,
        patch("builtins.input", return_value="Fix scrolling"),
        patch("context_forge.main.build_generation_service") as build_service,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: invalid provider configuration\n"

    build_service.assert_not_called()
    log_failed.assert_not_called()


def test_main_reports_unsupported_provider_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = [
        "context-forge",
        str(tmp_path),
        "--provider",
        "unknown",
    ]

    with (
        patch.object(sys, "argv", argv),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("context_forge.main.log_generation_failed") as log_failed,
        patch("builtins.input", return_value="Fix scrolling"),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Unsupported provider: unknown\n"

    build_service.assert_not_called()
    log_failed.assert_not_called()


@pytest.mark.parametrize("task", ("", "   \t  "))
def test_main_rejects_empty_task(
    task: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge", str(tmp_path)]),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("builtins.input", return_value=task),
        patch("context_forge.main.build_generation_service"),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Task cannot be empty\n"


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
        patch.object(
            sys,
            "argv",
            ["context-forge", "analyze", "."],
        ),
        patch(
            "context_forge.main.ProjectAnalyzer",
        ) as analyzer,
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


def test_legacy_path_invocation_uses_generate_command() -> None:
    with patch.object(
        sys,
        "argv",
        ["context-forge", "."],
    ):
        args = __import__("context_forge.main", fromlist=["parse_args"]).parse_args()

    assert args.command == "generate"
    assert args.path == Path(".")


def test_explicit_generate_command_parses_provider_options() -> None:
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "generate",
            ".",
            "--provider",
            "deterministic",
            "--model",
            "test-model",
        ],
    ):
        args = __import__("context_forge.main", fromlist=["parse_args"]).parse_args()

    assert args.command == "generate"
    assert args.path == Path(".")
    assert args.provider == "deterministic"
    assert args.model == "test-model"


def test_generate_command_uses_explicit_task(
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = type(
        "Response",
        (),
        {"content": "Done."},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "generate",
                ".",
                "--task",
                "Explain authentication",
            ],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
    ):
        build_service.return_value.generate.return_value = response

        main()

    call = build_service.return_value.generate.call_args

    assert call.kwargs["task"] == "Explain authentication"

    captured = capsys.readouterr()

    assert captured.out == "\nDone.\n"
    assert captured.err == ""


def test_generate_command_strips_explicit_task() -> None:
    response = type(
        "Response",
        (),
        {"content": "Done."},
    )()

    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "generate",
                ".",
                "--task",
                "  Explain authentication  ",
            ],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
    ):
        build_service.return_value.generate.return_value = response

        main()

    call = build_service.return_value.generate.call_args

    assert call.kwargs["task"] == "Explain authentication"


def test_generate_command_rejects_empty_explicit_task(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "generate",
                ".",
                "--task",
                "   ",
            ],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Task cannot be empty\n"


def test_generate_command_reads_interactive_task(
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = type(
        "Response",
        (),
        {"content": "Done."},
    )()

    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "generate", "."],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
        patch("builtins.input", return_value="  Explain authentication  "),
    ):
        build_service.return_value.generate.return_value = response

        main()

    call = build_service.return_value.generate.call_args

    assert call.kwargs["task"] == "Explain authentication"

    captured = capsys.readouterr()

    assert captured.out == "\nDone.\n"
    assert captured.err == ""


def test_generate_command_rejects_empty_interactive_task(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "generate", "."],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("builtins.input", return_value="   "),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Task cannot be empty\n"


def test_generate_command_handles_eof(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "generate", "."],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch(
            "builtins.input",
            side_effect=EOFError,
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: Task input ended unexpectedly\n"


def test_generate_command_handles_keyboard_interrupt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "generate", "."],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch(
            "builtins.input",
            side_effect=KeyboardInterrupt,
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 130

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "\n"


def test_explicit_generate_command_parses_task() -> None:
    with patch.object(
        sys,
        "argv",
        [
            "context-forge",
            "generate",
            ".",
            "--task",
            "Explain the repository",
        ],
    ):
        args = parse_args()

    assert args.command == "generate"
    assert args.path == Path(".")
    assert args.task == "Explain the repository"


def test_analyze_command_reports_analysis_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["context-forge", "analyze", "."],
        ),
        patch("context_forge.main.ProjectAnalyzer") as analyzer,
    ):
        analyzer.return_value.analyze.side_effect = RuntimeError("analysis failed")

        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: analysis failed\n"


def test_generate_command_reports_generation_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "context-forge",
                "generate",
                ".",
                "--task",
                "Explain authentication",
            ],
        ),
        patch("context_forge.main.ProjectAnalyzer"),
        patch("context_forge.main.build_generation_service") as build_service,
    ):
        build_service.return_value.generate.side_effect = RuntimeError(
            "generation failed"
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Error: generation failed\n"


def test_parse_args_status_command(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["context-forge", "status", "/tmp/project"],
    )

    args = parse_args()

    assert args.command == "status"
    assert args.path == Path("/tmp/project")


def test_parse_args_cache_command(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["context-forge", "cache", "/tmp/project"],
    )

    args = parse_args()

    assert args.command == "cache"
    assert args.path == Path("/tmp/project")


def test_parse_args_inspect_command(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["context-forge", "inspect", "/tmp/project"],
    )

    args = parse_args()

    assert args.command == "inspect"
    assert args.path == Path("/tmp/project")


def test_parse_args_diagnostics_command(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["context-forge", "diagnostics", "/tmp/project"],
    )

    args = parse_args()

    assert args.command == "diagnostics"
    assert args.path == Path("/tmp/project")


def test_parse_args_legacy_repository_path_still_means_generate(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["context-forge", "/tmp/project"],
    )

    args = parse_args()

    assert args.command == "generate"
    assert args.path == Path("/tmp/project")


def test_run_status_does_not_analyze(monkeypatch, tmp_path):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("status must not analyze the repository")

    monkeypatch.setattr(
        "context_forge.main.ProjectAnalyzer.analyze",
        fail_if_called,
    )

    class FakeRepository:
        def check_cache_freshness(
            self,
            repository_key,
            fingerprints,
        ):
            class Freshness:
                is_fresh = True

            return Freshness()

    project = type(
        "Project",
        (),
        {
            "root_path": tmp_path,
            "name": "test-project",
            "analysis_status": "complete",
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

    monkeypatch.setattr(
        "context_forge.main.load_project_analysis",
        lambda root_path: (
            FakeRepository(),
            "/tmp/project",
            project,
            metadata,
        ),
    )

    monkeypatch.setattr(
        "context_forge.main.current_fingerprints",
        lambda project: {},
    )

    run_status(tmp_path)


def test_load_project_analysis_requires_persisted_analysis(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "context_forge.main.ProjectRepository.load_analysis",
        lambda self, repository_key: None,
    )

    with pytest.raises(
        ValueError,
        match="No persisted analysis found; run 'context-forge analyze' first",
    ):
        load_project_analysis(tmp_path)


def test_load_project_analysis_does_not_analyze(
    tmp_path,
    monkeypatch,
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("loading persisted analysis must not analyze")

    monkeypatch.setattr(
        "context_forge.main.ProjectAnalyzer.analyze",
        fail_if_called,
    )

    monkeypatch.setattr(
        "context_forge.main.ProjectRepository.load_analysis",
        lambda self, repository_key: None,
    )

    with pytest.raises(
        ValueError,
        match="No persisted analysis found",
    ):
        load_project_analysis(tmp_path)
