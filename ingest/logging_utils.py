"""Shared logging helpers for ingest and root scripts."""

import logging
import os
from pathlib import Path


LOG_LEVEL_ENV_VAR = "LOG_LEVEL"
LOG_LEVEL_DEFAULT = "DEBUG"
LOG_LEVEL_CHOICES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_FILE_ENV_VAR = "LOG_FILE"
LOG_FILE_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "pipeline.log"


def parse_log_level(level_name: str) -> int:
    """Convert a log-level name into the corresponding logging constant."""
    normalized_level = level_name.strip().upper()
    if normalized_level not in LOG_LEVEL_CHOICES:
        allowed = ", ".join(LOG_LEVEL_CHOICES)
        raise ValueError(
            f"Invalid LOG_LEVEL '{level_name}'. Allowed values: {allowed}."
        )
    return getattr(logging, normalized_level)


def resolve_log_level() -> str:
    """Return effective log level from environment, defaulting to DEBUG."""
    return os.environ.get(LOG_LEVEL_ENV_VAR, LOG_LEVEL_DEFAULT)


def resolve_log_file() -> Path:
    """Return effective log file path from environment or default value."""
    configured_path = os.environ.get(LOG_FILE_ENV_VAR)
    if configured_path:
        return Path(configured_path)
    return LOG_FILE_DEFAULT


def configure_logging() -> str:
    """Configure console and file logging and return effective level name."""
    level_name = resolve_log_level()
    level_value = parse_log_level(level_name)
    log_file = resolve_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level_value)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level_value)
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=level_value, handlers=[console_handler, file_handler], force=True
    )
    return level_name.strip().upper()


def get_logger(name: str) -> logging.Logger:
    """Return a module logger configured by `configure_logging`."""
    return logging.getLogger(name)
