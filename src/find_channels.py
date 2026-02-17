#!/usr/bin/env python3
"""
One-time script to find YouTube channel IDs by search query.

Usage:
    python src/find_channels.py
"""

import httplib2
import json
import logging
import os
import sys

from dotenv import load_dotenv
from googleapiclient.discovery import build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNELS_PATH = os.path.join(PROJECT_ROOT, "config", "channels.json")
ENV_PATH = os.path.join(PROJECT_ROOT, "config", ".env")


def load_channels() -> dict:
    with open(CHANNELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_channels(data: dict) -> None:
    with open(CHANNELS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("channels.json updated")


def find_channel_id(youtube, search_query: str) -> str | None:
    """Search YouTube for a channel by query, return channel ID or None."""
    try:
        request = youtube.search().list(
            q=search_query,
            type="channel",
            maxResults=1,
            part="snippet",
        )
        response = request.execute()
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
        return None
    except Exception as e:
        logger.error("Error searching for '%s': %s", search_query, e)
        return None


def main() -> None:
    load_dotenv(ENV_PATH)
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY not set in config/.env")
        sys.exit(1)

    http = httplib2.Http(disable_ssl_certificate_validation=True)
    youtube = build("youtube", "v3", developerKey=api_key, http=http)
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
