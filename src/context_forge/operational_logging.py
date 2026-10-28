from __future__ import annotations

import logging
import logging.handlers
from logging.handlers import RotatingFileHandler
from pathlib import Path

from context_forge.config.global_config import global_config_directory

_LOGGER_NAME = "context_forge"
_LOG_FILENAME = "context-forge.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3
_OPERATIONAL_HANDLER_TAG = "_context_forge_operational"


def log_path() -> Path:
    return global_config_directory() / "logs" / _LOG_FILENAME


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    destination = log_path().resolve()

    matching_handler: RotatingFileHandler | None = None
    stale_handlers: list[RotatingFileHandler] = []

    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler_path = Path(handler.baseFilename).resolve()
            if handler_path == destination:
                if matching_handler is None:
                    matching_handler = handler
                else:
                    stale_handlers.append(handler)
            elif getattr(handler, _OPERATIONAL_HANDLER_TAG, False):
                stale_handlers.append(handler)

    for stale in stale_handlers:
        stale.close()
        logger.removeHandler(stale)

    if matching_handler is not None:
        return logger

    destination.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        destination,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    setattr(handler, _OPERATIONAL_HANDLER_TAG, True)

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
