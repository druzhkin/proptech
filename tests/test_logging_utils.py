from __future__ import annotations

import logging
from datetime import date

from src import logging_utils


def test_setup_logging_creates_daily_log_file_and_rotates_old_logs(tmp_path) -> None:
    """Logging bootstrap should create today's file and remove stale pipeline logs."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stale_log = logs_dir / "pipeline-2026-02-01.log"
    stale_log.write_text("old\n", encoding="utf-8")

    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level

    try:
        log_path = logging_utils.setup_logging(
            tmp_path,
            today=date(2026, 3, 26),
        )
        logging.getLogger("tests.logging").info("hello from logging utils")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert log_path == logs_dir / "pipeline-2026-03-26.log"
        assert log_path.exists()
        assert "hello from logging utils" in log_path.read_text(encoding="utf-8")
        assert not stale_log.exists()
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers.clear()
        for handler in original_handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(original_level)
