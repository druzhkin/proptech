#!/usr/bin/env python3
"""Shared logging setup for CLI entrypoints."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
LOG_RETENTION_DAYS = 30
LOG_FILE_PATTERN = re.compile(r"^pipeline-(\d{4}-\d{2}-\d{2})\.log$")


def _log_filename(for_date: date) -> str:
    """Build the daily log filename."""
    return f"pipeline-{for_date.isoformat()}.log"


def cleanup_old_logs(
    logs_dir: Path,
    *,
    today: date | None = None,
    retention_days: int = LOG_RETENTION_DAYS,
) -> None:
    """Delete pipeline log files older than the retention window."""
    reference_date = today or datetime.now(timezone.utc).date()
    cutoff_date = reference_date - timedelta(days=retention_days)

    for log_path in logs_dir.glob("pipeline-*.log"):
        match = LOG_FILE_PATTERN.match(log_path.name)
        if not match:
            continue

        try:
            log_date = date.fromisoformat(match.group(1))
        except ValueError:
            continue

        if log_date < cutoff_date:
            log_path.unlink(missing_ok=True)


def setup_logging(
    project_root: Path,
    *,
    level: int = logging.INFO,
    today: date | None = None,
    retention_days: int = LOG_RETENTION_DAYS,
) -> Path:
    """Configure root logging for CLI execution and return the active log path."""
    reference_date = today or datetime.now(timezone.utc).date()
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_logs(
        logs_dir,
        today=reference_date,
        retention_days=retention_days,
    )

    log_path = logs_dir / _log_filename(reference_date)
    formatter = logging.Formatter(LOG_FORMAT)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_path, encoding="utf-8")

    for handler in (stream_handler, file_handler):
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return log_path
