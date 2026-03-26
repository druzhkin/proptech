#!/usr/bin/env python3
"""Generate Telegram post drafts from collected articles."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "config" / ".env"
ARTICLES_DIR = PROJECT_ROOT / "data" / "articles"
DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"

FilterArticlesCallable = Callable[..., list[dict[str, Any]]]
GenerateValidatedCallable = Callable[..., tuple[dict[str, str], list[str]]]


class ExitCode(IntEnum):
    """CLI exit codes for draft generation."""

    SUCCESS = 0
    PARTIAL_FAILURE = 1
    FAILURE = 2


def _load_logging_setup() -> Callable[[Path], Path]:
    """Import the shared logging setup for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.logging_utils import setup_logging
    else:
        from .logging_utils import setup_logging

    return setup_logging


def _load_claude_client() -> tuple[FilterArticlesCallable, GenerateValidatedCallable]:
    """Import generation helpers in a way that works for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.claude_client import filter_articles, generate_validated_post
    else:
        from .claude_client import filter_articles, generate_validated_post

    return filter_articles, generate_validated_post


def _resolve_articles_file(requested_date: str | None = None) -> Path:
    """Resolve the article JSON file to use for draft generation."""
    if requested_date:
        file_path = ARTICLES_DIR / f"{requested_date}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Articles file not found for date {requested_date}")
        return file_path

    today_path = ARTICLES_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    if today_path.exists():
        return today_path

    available_files = sorted(ARTICLES_DIR.glob("*.json"))
    if not available_files:
        raise FileNotFoundError("No collected articles found in data/articles")
    return available_files[-1]


def load_articles(requested_date: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Load articles for draft generation and return the source date plus records."""
    file_path = _resolve_articles_file(requested_date)
    with file_path.open("r", encoding="utf-8") as f:
        articles = json.load(f)

    if not isinstance(articles, list):
        raise ValueError("Articles file must contain a list")

    normalized_articles = [article for article in articles if isinstance(article, dict)]
    return file_path.stem, normalized_articles


def _is_evergreen_placeholder(article: dict[str, Any]) -> bool:
    """Check whether an article is an evergreen fallback placeholder."""
    return str(article.get("url", "")).startswith("evergreen://")


def _build_draft_record(
    article: dict[str, Any],
    *,
    status: str,
    text: str = "",
    category: str = "",
    validation_errors: list[str] | None = None,
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    """Build a serialized draft record."""
    return {
        "id": str(uuid.uuid4()),
        "article_id": article.get("id", ""),
        "source_type": article.get("source_type", ""),
        "source_name": article.get("source_name", ""),
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "image_url": article.get("image_url"),
        "category": category,
        "text": text,
        "status": status,
        "validation_errors": validation_errors or [],
        "rejection_reason": rejection_reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def save_drafts(drafts_date: str, new_records: list[dict[str, Any]]) -> str:
    """Save draft records and preserve terminal/admin-reviewed entries on reruns."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DRAFTS_DIR / f"{drafts_date}.json"

    existing_records: list[dict[str, Any]] = []
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, list):
            existing_records = [record for record in loaded if isinstance(record, dict)]

    merged_records: dict[str, dict[str, Any]] = {}
    for record in existing_records:
        article_id = str(record.get("article_id", ""))
        if article_id:
            merged_records[article_id] = record

    for record in new_records:
        article_id = str(record.get("article_id", ""))
        if not article_id:
            continue

        existing = merged_records.get(article_id)
        if existing and (
            existing.get("status") in {"published", "skipped"}
            or bool(existing.get("edited_by_admin"))
        ):
            continue
        merged_records[article_id] = record

    final_records = list(merged_records.values())
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(final_records, f, indent=2, ensure_ascii=False)

    return str(file_path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the draft generation workflow and return a process exit code."""
    parser = argparse.ArgumentParser(description="PropTech draft generator")
    parser.add_argument("--max", type=int, default=5, help="Maximum number of drafts to generate")
    parser.add_argument("--date", default=None, help="Specific article date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    setup_logging = _load_logging_setup()
    log_path = setup_logging(PROJECT_ROOT)
    load_dotenv(ENV_PATH)
    logger.info("Logging to %s", log_path)

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("Missing required environment variable: OPENROUTER_API_KEY")
        return ExitCode.FAILURE

    try:
        articles_date, articles = load_articles(args.date)
    except Exception:
        logger.exception("Failed to load collected articles for generation")
        return ExitCode.FAILURE

    logger.info("Loaded %d articles from %s", len(articles), articles_date)
    if not articles:
        logger.warning("No articles available for generation")
        return ExitCode.FAILURE

    evergreen_articles = [
        article
        for article in articles
        if _is_evergreen_placeholder(article)
    ]
    source_backed_articles = [
        article
        for article in articles
        if not _is_evergreen_placeholder(article)
    ]

    filter_articles, generate_validated_post = _load_claude_client()

    rejected_records = [
        _build_draft_record(
            article,
            status="rejected",
            rejection_reason="evergreen_placeholder_requires_source_link",
        )
        for article in evergreen_articles
    ]

    if not source_backed_articles:
        logger.warning("No source-backed articles available for generation")
        if rejected_records:
            draft_path = save_drafts(articles_date, rejected_records)
            logger.info("Saved %d rejected records to %s", len(rejected_records), draft_path)
            return ExitCode.PARTIAL_FAILURE
        return ExitCode.FAILURE

    selected_articles = filter_articles(
        api_key,
        source_backed_articles,
        max_items=args.max,
    )
    logger.info("Selected %d articles for generation", len(selected_articles))

    draft_records: list[dict[str, Any]] = []
    for article in selected_articles:
        try:
            post_result, validation_errors = generate_validated_post(api_key, article)
        except Exception:
            logger.exception("Draft generation failed for article %s", article.get("id", "unknown"))
            draft_records.append(
                _build_draft_record(
                    article,
                    status="rejected",
                    rejection_reason="generation_failed",
                )
            )
            continue

        if validation_errors:
            draft_records.append(
                _build_draft_record(
                    article,
                    status="rejected",
                    text=post_result.get("text", ""),
                    category=post_result.get("category", ""),
                    validation_errors=validation_errors,
                    rejection_reason="validation_failed",
                )
            )
            continue

        draft_records.append(
            _build_draft_record(
                article,
                status="draft",
                text=post_result["text"],
                category=post_result["category"],
            )
        )

    all_records = draft_records + rejected_records
    if all_records:
        draft_path = save_drafts(articles_date, all_records)
        logger.info("Saved %d draft records to %s", len(all_records), draft_path)
    else:
        logger.warning("No draft records were produced")
        return ExitCode.FAILURE

    draft_count = sum(record["status"] == "draft" for record in draft_records)
    rejected_count = sum(record["status"] == "rejected" for record in all_records)
    logger.info("Draft generation summary: drafts=%d rejected=%d", draft_count, rejected_count)

    if draft_count and not rejected_count:
        return ExitCode.SUCCESS
    if draft_count or rejected_count:
        return ExitCode.PARTIAL_FAILURE
    return ExitCode.FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
