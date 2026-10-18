from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from context_forge.config.global_config import global_config_directory

_LOGGER_NAME = "context_forge"
_LOG_FILENAME = "context-forge.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def log_path() -> Path:
    return global_config_directory() / "logs" / _LOG_FILENAME


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    destination = log_path()

    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == destination.resolve()
        ):
            return logger

    destination.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        destination,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )

    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    logger.addHandler(handler)

    return logger


def _log_event(
    level: int,
    message: str,
    *args: object,
) -> None:
    try:
        get_logger().log(level, message, *args)
    except OSError:
        # Operational logging must not interrupt application beihaviour
        pass


def log_analysis_started(
    *,
    project_path: Path,
) -> None:
    _log_event(
        logging.INFO,
        "analysis_started project=%s",
        project_path,
    )


def log_analysis_completed(
    *,
    project_path: Path,
    duration_seconds: float,
    files_count: int,
    symbols_count: int,
) -> None:
    _log_event(
        logging.INFO,
        "analysis_completed project=%s duration=%.3f files=%d symbols=%d",
        project_path,
        duration_seconds,
        files_count,
        symbols_count,
    )


def log_analysis_failed(
    *,
    project_path: Path,
    duration_seconds: float,
    error: Exception,
) -> None:
    _log_event(
        logging.ERROR,
        "analysis_failed project=%s duration=%.3f error_type=%s error=%s",
        project_path,
        duration_seconds,
        type(error).__name__,
        error,
    )
