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


def log_generation_started(
    *,
    project_path: Path,
    provider: str,
    model: str,
) -> None:
    get_logger().info(
        "generation_started project=%s provider=%s model=%s",
        project_path,
        provider,
        model,
    )


def log_generation_completed(
    *,
    project_path: Path,
    provider: str,
    model: str,
    duration_seconds: float,
) -> None:
    get_logger().info(
        "generation_completed project=%s provider=%s model=%s duration=%.3f",
        project_path,
        provider,
        model,
        duration_seconds,
    )


def log_generation_failed(
    *,
    project_path: Path,
    provider: str | None,
    model: str | None,
    duration_seconds: float,
    error: Exception,
) -> None:
    get_logger().error(
        "generation_failed project=%s provider=%s model=%s "
        "duration=%.3f error_type=%s error=%s",
        project_path,
        provider,
        model,
        duration_seconds,
        type(error).__name__,
        error,
    )
