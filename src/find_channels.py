#!/usr/bin/env python3
"""
One-time script to find YouTube channel IDs by search query.

Usage:
    python src/find_channels.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANNELS_PATH = PROJECT_ROOT / "config" / "channels.json"
ENV_PATH = PROJECT_ROOT / "config" / ".env"
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _should_retry_http_error(exc: BaseException) -> bool:
    """Retry only transient YouTube Data API failures."""
    if isinstance(exc, HttpError):
        status_code = getattr(exc, "status_code", None)
        if status_code is None and getattr(exc, "resp", None) is not None:
            status_code = getattr(exc.resp, "status", None)
        return status_code in TRANSIENT_HTTP_STATUS_CODES
    return True


def _load_logging_setup() -> Any:
    """Import the shared logging setup for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.logging_utils import setup_logging
    else:
        from .logging_utils import setup_logging

    return setup_logging


def load_channels() -> dict[str, list[dict[str, str]]]:
    with CHANNELS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_channels(data: dict[str, list[dict[str, str]]]) -> None:
    with CHANNELS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("channels.json updated")


def find_channel_id(youtube: Any, search_query: str) -> str | None:
    """Search YouTube for a channel by query, return channel ID or None."""
    if __package__ in (None, "") and str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.retry_utils import retry_call

    try:
        request = youtube.search().list(
            q=search_query,
            type="channel",
            maxResults=1,
            part="snippet",
        )
        response = retry_call(
            request.execute,
            operation=f"YouTube channel search for {search_query}",
            retry_exceptions=(HttpError, OSError, TimeoutError),
            should_retry=_should_retry_http_error,
            logger=logger,
        )
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
        return None
    except Exception as e:
        logger.error("Error searching for '%s': %s", search_query, e)
        return None


def main() -> None:
    setup_logging = _load_logging_setup()
    log_path = setup_logging(PROJECT_ROOT)
    load_dotenv(ENV_PATH)
    logger.info("Logging to %s", log_path)
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY not set in config/.env")
        sys.exit(1)

    youtube = build("youtube", "v3", developerKey=api_key)
    data = load_channels()

    found = 0
    skipped = 0
    failed = 0

    for channel in data["channels"]:
        if channel.get("channel_id"):
            logger.info("SKIP %s — already has channel_id", channel["name"])
            skipped += 1
            continue

        channel_id = find_channel_id(youtube, channel["search_query"])
        if channel_id:
            channel["channel_id"] = channel_id
            logger.info("FOUND %s → %s", channel["name"], channel_id)
            found += 1
        else:
            logger.warning("NOT FOUND %s (query: %s)", channel["name"], channel["search_query"])
            failed += 1

    save_channels(data)

    logger.info("--- Results ---")
    logger.info("Found: %d", found)
    logger.info("Already had ID: %d", skipped)
    logger.info("Not found: %d", failed)
    logger.info("Total: %d", len(data["channels"]))


if __name__ == "__main__":
    main()
