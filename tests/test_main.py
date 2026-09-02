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
    main,
    resolve_project_path,
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
