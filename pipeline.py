#!/usr/bin/env python3
"""Pipeline CLI entry point: collect articles first, then generate drafts."""

from __future__ import annotations

from src.pipeline_runner import run_pipeline


def main() -> int:
    """Run the pipeline sequentially from the standalone CLI."""
    return run_pipeline()


if __name__ == "__main__":
    raise SystemExit(main())
