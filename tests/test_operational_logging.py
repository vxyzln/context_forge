import io
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.operational_logging import (
    _MAX_BYTES,
    _log_event,
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

    assert " INFO " in content
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

    assert " INFO " in content
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

    assert " ERROR " in content
    assert "analysis_failed" in content
    assert "project=/tmp/project" in content
    assert "duration=0.456" in content
    assert "error_type=ValueError" in content
    assert "error=corrupt index" in content


@pytest.mark.parametrize(
    ("log_function", "kwargs"),
    [
        (
            log_analysis_started,
            {"project_path": Path("/tmp/project")},
        ),
        (
            log_analysis_completed,
            {
                "project_path": Path("/tmp/project"),
                "duration_seconds": 1.234,
                "files_count": 12,
                "symbols_count": 45,
            },
        ),
        (
            log_analysis_failed,
            {
                "project_path": Path("/tmp/project"),
                "duration_seconds": 0.456,
                "error": ValueError("corrupt index"),
            },
        ),
    ],
    ids=["analysis-started", "analysis-completed", "analysis-failed"],
)
def test_logging_filesystem_errors_do_not_escape(
    log_function,
    kwargs: dict[str, object],
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        side_effect=OSError("log directory unavailable"),
    ):
        log_function(**kwargs)


def test_get_logger_idempotency_and_no_duplicate_handlers(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        logger1 = get_logger()
        logger2 = get_logger()
        logger3 = get_logger()

        assert logger1 is logger2 is logger3
        rotating_handlers = [
            h for h in logger1.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(rotating_handlers) == 1
        assert logger1.level == logging.INFO
        assert not logger1.propagate

        logger1.info("event_one")
        logger2.info("event_two")

        for handler in logger1.handlers:
            handler.flush()

        log_file = tmp_path / "logs" / "context-forge.log"
        lines = [
            line for line in log_file.read_text(encoding="utf-8").splitlines() if line
        ]
        assert len(lines) == 2
        assert "event_one" in lines[0]
        assert "event_two" in lines[1]


def test_get_logger_handles_destination_change_without_leaking_or_duplicating(
    tmp_path: Path,
) -> None:
    dir1 = tmp_path / "config1"
    dir2 = tmp_path / "config2"

    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=dir1,
    ):
        logger1 = get_logger()
        logger1.info("first_destination_message")
        for handler in logger1.handlers:
            handler.flush()

    file1 = dir1 / "logs" / "context-forge.log"
    assert file1.exists()
    assert "first_destination_message" in file1.read_text(encoding="utf-8")

    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=dir2,
    ):
        logger2 = get_logger()
        rotating_handlers = [
            h for h in logger2.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(rotating_handlers) == 1

        logger2.info("second_destination_message")
        for handler in logger2.handlers:
            handler.flush()

    file2 = dir2 / "logs" / "context-forge.log"
    assert file2.exists()
    assert "second_destination_message" in file2.read_text(encoding="utf-8")

    file1_content = file1.read_text(encoding="utf-8")
    assert "second_destination_message" not in file1_content


def test_get_logger_cleans_up_duplicate_handlers_for_same_destination(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        dest = log_path().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("context_forge")
        h1 = RotatingFileHandler(
            dest, maxBytes=_MAX_BYTES, backupCount=3, encoding="utf-8"
        )
        h2 = RotatingFileHandler(
            dest, maxBytes=_MAX_BYTES, backupCount=3, encoding="utf-8"
        )
        logger.addHandler(h1)
        logger.addHandler(h2)
        initial_rotating = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(initial_rotating) == 2

        logger_resolved = get_logger()
        final_rotating = [
            h for h in logger_resolved.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(final_rotating) == 1
        assert final_rotating[0] is h1


def test_get_logger_preserves_unrelated_handlers(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        logger = logging.getLogger("context_forge")
        stream_handler = logging.StreamHandler(io.StringIO())
        custom_dest = tmp_path / "custom.log"
        other_rotating = RotatingFileHandler(custom_dest, encoding="utf-8")

        logger.addHandler(stream_handler)
        logger.addHandler(other_rotating)

        get_logger()

        assert stream_handler in logger.handlers
        assert other_rotating in logger.handlers
        assert any(
            isinstance(h, RotatingFileHandler)
            and Path(h.baseFilename).name == "context-forge.log"
            for h in logger.handlers
        )

        other_rotating.close()


def test_get_logger_preserves_unrelated_rotating_handler_with_same_filename(
    tmp_path: Path,
) -> None:
    unrelated_dir = tmp_path / "other_service"
    unrelated_dir.mkdir(parents=True, exist_ok=True)
    unrelated_file = unrelated_dir / "context-forge.log"

    unrelated_handler = RotatingFileHandler(unrelated_file, encoding="utf-8")
    logger = logging.getLogger("context_forge")
    logger.addHandler(unrelated_handler)

    try:
        with patch(
            "context_forge.operational_logging.global_config_directory",
            return_value=tmp_path / "cf_config",
        ):
            cf_logger = get_logger()

            assert unrelated_handler in cf_logger.handlers

            cf_logger.info("message_for_all_handlers")
            unrelated_handler.flush()

            unrelated_content = unrelated_file.read_text(encoding="utf-8")
            assert "message_for_all_handlers" in unrelated_content
    finally:
        unrelated_handler.close()
        logger.removeHandler(unrelated_handler)


def test_log_record_formatting_structure(
    tmp_path: Path,
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        logger = get_logger()
        logger.info("format_check_event key=val")

        for handler in logger.handlers:
            handler.flush()

        log_file = tmp_path / "logs" / "context-forge.log"
        line = log_file.read_text(encoding="utf-8").strip()

        pattern = (
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4})\s+(INFO|ERROR)\s+(.*)$"
        )
        match = re.match(pattern, line)
        assert match is not None, f"Log line does not match expected format: {line}"
        assert match.group(2) == "INFO"
        assert match.group(3) == "format_check_event key=val"


def test_log_rotation_and_backup_count(
    tmp_path: Path,
) -> None:
    test_max_bytes = 150
    test_backups = 2

    with (
        patch(
            "context_forge.operational_logging.global_config_directory",
            return_value=tmp_path,
        ),
        patch("context_forge.operational_logging._MAX_BYTES", test_max_bytes),
        patch("context_forge.operational_logging._BACKUP_COUNT", test_backups),
    ):
        logger = get_logger()

        for i in range(6):
            logger.info("entry_%d_%s", i, "UnicodeData-ümlaut-🚀-" + "A" * 60)

        for handler in logger.handlers:
            handler.flush()

        log_dir = tmp_path / "logs"
        active_log = log_dir / "context-forge.log"
        backup1 = log_dir / "context-forge.log.1"
        backup2 = log_dir / "context-forge.log.2"
        backup3 = log_dir / "context-forge.log.3"

        assert active_log.exists()
        assert backup1.exists()
        assert backup2.exists()
        assert not backup3.exists()

        assert "UnicodeData-ümlaut-🚀" in active_log.read_text(encoding="utf-8")
        assert "UnicodeData-ümlaut-🚀" in backup1.read_text(encoding="utf-8")
        assert "UnicodeData-ümlaut-🚀" in backup2.read_text(encoding="utf-8")


def test_logging_tolerates_mkdir_failure(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "context_forge.operational_logging.global_config_directory",
            return_value=tmp_path,
        ),
        patch(
            "pathlib.Path.mkdir",
            side_effect=PermissionError("read-only filesystem"),
        ),
    ):
        log_analysis_started(project_path=Path("/tmp/project"))
        log_analysis_completed(
            project_path=Path("/tmp/project"),
            duration_seconds=1.0,
            files_count=1,
            symbols_count=1,
        )
        log_analysis_failed(
            project_path=Path("/tmp/project"),
            duration_seconds=1.0,
            error=RuntimeError("err"),
        )


def test_logging_tolerates_handler_construction_failure(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "context_forge.operational_logging.global_config_directory",
            return_value=tmp_path,
        ),
        patch(
            "context_forge.operational_logging.RotatingFileHandler",
            side_effect=PermissionError("cannot open log file"),
        ),
    ):
        with pytest.raises(PermissionError, match="cannot open log file"):
            get_logger()

        log_analysis_started(project_path=Path("/tmp/project"))
        log_analysis_completed(
            project_path=Path("/tmp/project"),
            duration_seconds=1.0,
            files_count=1,
            symbols_count=1,
        )
        log_analysis_failed(
            project_path=Path("/tmp/project"),
            duration_seconds=1.0,
            error=RuntimeError("err"),
        )


def test_record_write_failure_behavior(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch(
        "context_forge.operational_logging.global_config_directory",
        return_value=tmp_path,
    ):
        logger = get_logger()
        rotating_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(rotating_handlers) == 1
        handler = rotating_handlers[0]

        with patch.object(
            handler.stream,
            "write",
            side_effect=OSError(28, "No space left on device"),
        ):
            log_analysis_started(project_path=Path("/tmp/project"))
            log_analysis_completed(
                project_path=Path("/tmp/project"),
                duration_seconds=1.23,
                files_count=5,
                symbols_count=10,
            )
            log_analysis_failed(
                project_path=Path("/tmp/project"),
                duration_seconds=0.45,
                error=RuntimeError("original analysis error"),
            )

        captured = capsys.readouterr()
        assert "No space left on device" in captured.err
        assert "Logging error" in captured.err


def test_logging_does_not_mask_programming_errors() -> None:
    with pytest.raises(TypeError):
        _log_event("not_an_int_level", "msg")
