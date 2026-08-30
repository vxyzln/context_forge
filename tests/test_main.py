import sys
from unittest.mock import patch

import pytest

from context_forge.main import main
from context_forge.provider import ProviderConfig


def test_main_reports_provider_error_without_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["context-forge"]),
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
        patch.object(sys, "argv", ["context-forge"]),
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
        model="qwen3:8b",
        temperature=0.0,
        max_tokens=None,
        base_url="http://localhost:11434",
    )

    with (
        patch.object(sys, "argv", ["context-forge"]),
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
        patch.object(sys, "argv", ["context-forge"]),
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
