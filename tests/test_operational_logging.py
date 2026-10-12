import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.operational_logging import (
    get_logger,
    log_analysis_completed,
    log_analysis_failed,
    log_analysis_started,
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


def test_analysis_started_logs_operational_metadata(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_analysis_started(
            project_path=Path("/tmp/project"),
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert "analysis_started" in content
    assert "project=/tmp/project" in content


def test_analysis_completed_logs_duration_and_counts(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_analysis_completed(
            project_path=Path("/tmp/project"),
            duration_seconds=1.234,
            files_count=12,
            symbols_count=45,
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert "analysis_completed" in content
    assert "project=/tmp/project" in content
    assert "duration=1.234" in content
    assert "files=12" in content
    assert "symbols=45" in content


def test_analysis_failed_logs_error_metadata(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        log_analysis_failed(
            project_path=Path("/tmp/project"),
            duration_seconds=0.456,
            error=ValueError("corrupt index"),
        )

        logger = get_logger()

        for handler in logger.handlers:
            handler.flush()

        content = (tmp_path / "logs" / "context-forge.log").read_text(encoding="utf-8")

    assert "analysis_failed" in content
    assert "project=/tmp/project" in content
    assert "duration=0.456" in content
    assert "error_type=ValueError" in content
    assert "error=corrupt index" in content
