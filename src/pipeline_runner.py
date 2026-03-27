#!/usr/bin/env python3
"""Shared pipeline runner used by both CLI and the long-running bot service."""

from __future__ import annotations

import logging
from pathlib import Path

from .collect import ExitCode as CollectExitCode
from .collect import main as collect_main
from .generate import ExitCode as GenerateExitCode
from .generate import main as generate_main
from .logging_utils import setup_logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def run_pipeline(*, configure_logging: bool = True) -> int:
    """Run collect first, then generate, and return the resulting exit code."""
    if configure_logging:
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
