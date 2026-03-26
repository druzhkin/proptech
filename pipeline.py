#!/usr/bin/env python3
"""Pipeline entry point: collect articles first, then generate drafts."""

from __future__ import annotations

import logging
from pathlib import Path

from src.collect import ExitCode as CollectExitCode
from src.collect import main as collect_main
from src.generate import ExitCode as GenerateExitCode
from src.generate import main as generate_main
from src.logging_utils import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def main() -> int:
    """Run the pipeline sequentially and return the resulting exit code."""
    log_path = setup_logging(PROJECT_ROOT)
    logger.info("Pipeline logging to %s", log_path)

    collect_exit = int(collect_main([]))
    if collect_exit != CollectExitCode.SUCCESS:
        logger.error(
            "Collect step exited with code %d. Generate step will not start.",
            collect_exit,
        )
        return collect_exit

    generate_exit = int(generate_main([]))
    if generate_exit == GenerateExitCode.SUCCESS:
        logger.info("Pipeline completed successfully")
        return GenerateExitCode.SUCCESS

    logger.warning("Generate step exited with code %d", generate_exit)
    return generate_exit


if __name__ == "__main__":
    raise SystemExit(main())
