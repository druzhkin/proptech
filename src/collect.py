#!/usr/bin/env python3
"""
Main collection script. Combines Perplexity + YouTube sources.

Usage:
    python src/collect.py                      # Perplexity + YouTube
    python src/collect.py --engine perplexity   # Only Perplexity
    python src/collect.py --engine youtube      # Only YouTube

Output: data/articles/YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "config" / ".env"
CHANNELS_PATH = PROJECT_ROOT / "config" / "channels.json"
EVERGREEN_TOPICS_PATH = PROJECT_ROOT / "config" / "evergreen_topics.json"
ARTICLES_DIR = PROJECT_ROOT / "data" / "articles"

SearchNewsCallable = Callable[[str], list[dict[str, Any]]]
CollectVideosCallable = Callable[[dict[str, Any], str], list[dict[str, Any]]]


class ExitCode(IntEnum):
    """CLI exit codes for collection runs."""

    SUCCESS = 0
    PARTIAL_FAILURE = 1
    FAILURE = 2


def _load_collectors() -> tuple[SearchNewsCallable, CollectVideosCallable]:
    """Import source collectors in a way that works for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.perplexity_client import search_proptech_news
        from src.youtube_client import collect_all_channels
    else:
        from .perplexity_client import search_proptech_news
        from .youtube_client import collect_all_channels

    return search_proptech_news, collect_all_channels


def _load_logging_setup() -> Callable[[Path], Path]:
    """Import the shared logging setup for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.logging_utils import setup_logging
    else:
        from .logging_utils import setup_logging

    return setup_logging


def deduplicate(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate articles by URL."""
    seen_urls: set[str] = set()
    unique: list[dict[str, Any]] = []
    for a in articles:
        url = a.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        unique.append(a)
    return unique


def load_channels() -> dict[str, Any]:
    """Load YouTube channel configuration from disk."""
    with CHANNELS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_evergreen_topics() -> list[dict[str, Any]]:
    """Load evergreen topics for fallback collection."""
    with EVERGREEN_TOPICS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("evergreen_topics.json must contain a list")

    topics: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            topics.append(item)
    return topics


def build_evergreen_articles(limit: int = 5) -> list[dict[str, Any]]:
    """Convert evergreen topics into article-like placeholders for downstream use."""
    try:
        topics = load_evergreen_topics()
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        logger.exception("Failed to load evergreen topics")
        return []

    available_topics = [topic for topic in topics if not topic.get("used", False)]
    selected_topics = (available_topics or topics)[:limit]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    evergreen_articles: list[dict[str, Any]] = []
    for topic in selected_topics:
        title = str(topic.get("title", "")).strip()
        if not title:
            continue

        category_hint = str(topic.get("category", "evergreen")).strip() or "evergreen"
        topic_id = str(topic.get("id", "unknown")).strip() or "unknown"
        evergreen_articles.append(
            {
                "id": topic_id,
                "source_type": "perplexity",
                "source_name": "Evergreen Topics",
                "title": title,
                "url": f"evergreen://{topic_id}",
                "text": (
                    f"Evergreen topic fallback. Theme: {title}. "
                    f"Category: {category_hint}. "
                    "This is a placeholder topic rather than a sourced news article."
                ),
                "image_url": None,
                "date": today,
                "category_hint": category_hint,
                "collected_at": now_iso,
            }
        )

    return evergreen_articles


def save_articles(articles: list[dict[str, Any]]) -> str:
    """Save articles to data/articles/YYYY-MM-DD.json. Returns file path."""
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = ARTICLES_DIR / f"{today}.json"

    # If file exists, merge with existing
    existing: list[dict[str, Any]] = []
    if filepath.exists():
        with filepath.open("r", encoding="utf-8") as f:
            existing = json.load(f)

    merged = existing + articles
    merged = deduplicate(merged)

    with filepath.open("w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    return str(filepath)


def _required_env_vars(
    *,
    run_perplexity: bool,
    run_youtube: bool,
) -> list[str]:
    """Return required env vars for the chosen collection engines."""
    required: list[str] = []
    if run_perplexity:
        required.append("PERPLEXITY_API_KEY")
    if run_youtube:
        required.append("YOUTUBE_API_KEY")
    return required


def main(argv: Sequence[str] | None = None) -> int:
    """Run the collection workflow and return a process exit code."""
    parser = argparse.ArgumentParser(description="PropTech news collector")
    parser.add_argument(
        "--engine",
        choices=["perplexity", "youtube"],
        default=None,
        help="Collect from specific engine only (default: both)",
    )
    args = parser.parse_args(argv)

    setup_logging = _load_logging_setup()
    log_path = setup_logging(PROJECT_ROOT)
    load_dotenv(ENV_PATH)
    logger.info("Logging to %s", log_path)

    run_perplexity = args.engine in (None, "perplexity")
    run_youtube = args.engine in (None, "youtube")
    missing_env_vars = [
        name
        for name in _required_env_vars(
            run_perplexity=run_perplexity,
            run_youtube=run_youtube,
        )
        if not os.getenv(name)
    ]
    if missing_env_vars:
        logger.error(
            "Missing required environment variables: %s",
            ", ".join(missing_env_vars),
        )
        return ExitCode.FAILURE

    search_proptech_news, collect_all_channels = _load_collectors()
    all_articles: list[dict[str, Any]] = []
    source_results: dict[str, bool] = {}

    # --- Perplexity ---
    if run_perplexity:
        api_key = os.getenv("PERPLEXITY_API_KEY")
        perplexity_articles: list[dict[str, Any]] = []
        perplexity_had_error = False
        try:
            perplexity_articles = search_proptech_news(api_key or "")
        except Exception:
            perplexity_had_error = True
            logger.exception("Perplexity failed")

        perplexity_provided_articles = bool(perplexity_articles)

        if not perplexity_articles and not perplexity_had_error:
            evergreen_articles = build_evergreen_articles()
            if evergreen_articles:
                perplexity_articles = evergreen_articles
                logger.warning(
                    "Perplexity returned no articles. Added %d evergreen topics.",
                    len(evergreen_articles),
                )
            else:
                logger.warning(
                    "Perplexity returned no articles and evergreen fallback is empty."
                )

        if perplexity_articles:
            all_articles.extend(perplexity_articles)
            logger.info("Perplexity: collected %d articles", len(perplexity_articles))
        source_results["perplexity"] = perplexity_provided_articles and not perplexity_had_error

    # --- YouTube ---
    if run_youtube:
        api_key = os.getenv("YOUTUBE_API_KEY")
        try:
            channels_config = load_channels()
            youtube_articles = collect_all_channels(channels_config, api_key or "")
            all_articles.extend(youtube_articles)
            source_results["youtube"] = True
            logger.info("YouTube: collected %d articles", len(youtube_articles))
        except Exception:
            source_results["youtube"] = False
            logger.exception("YouTube failed")

    # --- Deduplicate & Save ---
    all_articles = deduplicate(all_articles)
    if all_articles:
        filepath = save_articles(all_articles)
        logger.info("Saved %d articles to %s", len(all_articles), filepath)
    else:
        logger.warning("No articles collected")

    # --- Summary ---
    sources: dict[str, int] = {}
    for a in all_articles:
        source_name = str(a.get("source_type", "unknown"))
        sources[source_name] = sources.get(source_name, 0) + 1

    logger.info("=== Collection Summary ===")
    logger.info("Total articles: %d", len(all_articles))
    for src, count in sorted(sources.items()):
        logger.info("  %s: %d", src, count)

    if not all_articles:
        return ExitCode.FAILURE
    failures = sum(not status for status in source_results.values())
    if failures:
        return ExitCode.PARTIAL_FAILURE
    return ExitCode.SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
