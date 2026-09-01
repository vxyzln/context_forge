import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.operational_logging import (
    get_logger,
    log_generation_completed,
    log_generation_failed,
    log_generation_started,
    log_path,
)


@pytest.fixture(autouse=True)
def reset_logger() -> None:
    logger = logging.getLogger("context_forge")

    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def test_log_path_uses_application_configuration_directory(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        assert log_path() == tmp_path / "logs" / "context-forge.log"


def test_get_logger_creates_log_file(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        logger = get_logger()

        logger.info("test_event")

        for handler in logger.handlers:
            handler.flush()

        path = tmp_path / "logs" / "context-forge.log"

        assert path.exists()
        assert "test_event" in path.read_text(encoding="utf-8")


def test_generation_started_logs_operational_metadata(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_generation_started(
            project_path=Path("/tmp/project"),
            provider="ollama",
            model="qwen2.5-coder:7b",
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert "generation_started" in content
    assert "project=/tmp/project" in content
    assert "provider=ollama" in content
    assert "model=qwen2.5-coder:7b" in content


def test_generation_completed_logs_duration(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_generation_completed(
            project_path=Path("/tmp/project"),
            provider="ollama",
            model="qwen2.5-coder:7b",
            duration_seconds=1.234,
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert "generation_completed" in content
    assert "duration=1.234" in content


def test_generation_failed_logs_error_metadata_without_task(
    tmp_path: Path,
) -> None:
    error = RuntimeError("Ollama provider request timed out")

    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_generation_failed(
            project_path=Path("/tmp/project"),
            provider="ollama",
            model="qwen2.5-coder:7b",
            duration_seconds=60.123,
            error=error,
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert "generation_failed" in content
    assert "error_type=RuntimeError" in content
    assert "Ollama provider request timed out" in content
    assert "task=" not in content


def test_logging_does_not_record_generated_content_or_task(
    tmp_path: Path,
) -> None:
    task = "Explain the secret authentication implementation"
    response = "The secret implementation is in auth.py"

    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_generation_started(
            project_path=Path("/tmp/project"),
            provider="ollama",
            model="qwen2.5-coder:7b",
        )

        log_generation_completed(
            project_path=Path("/tmp/project"),
            provider="ollama",
            model="qwen2.5-coder:7b",
            duration_seconds=1.0,
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert task not in content
    assert response not in content
