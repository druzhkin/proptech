#!/usr/bin/env python3
"""
Main collection script. Combines Perplexity + YouTube sources.

Usage:
    python src/collect.py                      # Perplexity + YouTube
    python src/collect.py --engine perplexity   # Only Perplexity
    python src/collect.py --engine youtube      # Only YouTube

Output: data/articles/YYYY-MM-DD.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.perplexity_client import search_proptech_news
from src.youtube_client import collect_all_channels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(PROJECT_ROOT, "config", ".env")
CHANNELS_PATH = os.path.join(PROJECT_ROOT, "config", "channels.json")
ARTICLES_DIR = os.path.join(PROJECT_ROOT, "data", "articles")


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles by URL."""
    seen_urls: set[str] = set()
    unique = []
    for a in articles:
        url = a.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        unique.append(a)
    return unique


def load_channels() -> dict:
    with open(CHANNELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_articles(articles: list[dict]) -> str:
    """Save articles to data/articles/YYYY-MM-DD.json. Returns file path."""
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = os.path.join(ARTICLES_DIR, f"{today}.json")

    # If file exists, merge with existing
    existing = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = json.load(f)

    merged = existing + articles
    merged = deduplicate(merged)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    return filepath


def main() -> None:
    parser = argparse.ArgumentParser(description="PropTech news collector")
    parser.add_argument(
        "--engine",
        choices=["perplexity", "youtube"],
        default=None,
        help="Collect from specific engine only (default: both)",
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    run_perplexity = args.engine in (None, "perplexity")
    run_youtube = args.engine in (None, "youtube")

    all_articles: list[dict] = []

    # --- Perplexity ---
    if run_perplexity:
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            logger.warning("PERPLEXITY_API_KEY not set, skipping Perplexity")
        else:
            try:
                perplexity_articles = search_proptech_news(api_key)
                all_articles.extend(perplexity_articles)
                logger.info("Perplexity: collected %d articles", len(perplexity_articles))
            except Exception as e:
                logger.error("Perplexity failed: %s", e)

    # --- YouTube ---
    if run_youtube:
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set, skipping YouTube")
        else:
            try:
                channels_config = load_channels()
                youtube_articles = collect_all_channels(channels_config, api_key)
                all_articles.extend(youtube_articles)
                logger.info("YouTube: collected %d articles", len(youtube_articles))
            except Exception as e:
                logger.error("YouTube failed: %s", e)

    # --- Deduplicate & Save ---
    all_articles = deduplicate(all_articles)
    if all_articles:
        filepath = save_articles(all_articles)
        logger.info("Saved %d articles to %s", len(all_articles), filepath)
    else:
        logger.warning("No articles collected")

    # --- Summary ---
    sources = {}
    for a in all_articles:
        src = a.get("source_type", "unknown")
        sources[src] = sources.get(src, 0) + 1

    logger.info("=== Collection Summary ===")
    logger.info("Total articles: %d", len(all_articles))
    for src, count in sorted(sources.items()):
        logger.info("  %s: %d", src, count)


if __name__ == "__main__":
    main()
