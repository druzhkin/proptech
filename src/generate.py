#!/usr/bin/env python3
"""Generate Telegram post drafts from collected articles."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
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
DescribeEditorialCallable = Callable[[dict[str, Any]], dict[str, Any]]
TECH_SIGNAL_KEYWORDS = (
    "ai",
    "automation",
    "robot",
    "bim",
    "digital twin",
    "iot",
    "sensor",
    "computer vision",
    "workflow",
    "software",
    "platform",
    "tool",
    "deployment",
    "launched",
    "rollout",
    "integration",
    "simulation",
    "design",
    "prefab",
    "modular",
    "3d print",
    "drone",
    "\u0438\u0438",
    "\u0440\u043e\u0431\u043e\u0442",
    "\u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0437",
    "\u0446\u0438\u0444\u0440\u043e\u0432",
    "\u0434\u0430\u0442\u0447\u0438\u043a",
    "\u0438\u043d\u0442\u0435\u0433\u0440\u0430\u0446",
    "\u043c\u043e\u0434\u0435\u043b",
    "\u043f\u043b\u0430\u0442\u0444\u043e\u0440\u043c",
    "\u0434\u0432\u043e\u0439\u043d\u0438\u043a",
    "\u0441\u0438\u0441\u0442\u0435\u043c",
    "\u0441\u0442\u0440\u043e\u0439\u043a",
    "\u044d\u043a\u0441\u043f\u043b\u0443\u0430\u0442\u0430\u0446",
)
HIGH_INTEREST_TECH_KEYWORDS = (
    "ai",
    "computer vision",
    "generative",
    "autonomous",
    "robot",
    "robotics",
    "drone",
    "rtk",
    "digital twin",
    "iot",
    "sensor",
    "3d print",
    "3d printer",
    "prefab",
    "prefabricat",
    "modular",
    "offsite",
    "laser scan",
    "lidar",
    "machine vision",
)
BUSINESS_NOISE_KEYWORDS = (
    "funding",
    "raised",
    "raises",
    "series a",
    "series b",
    "series c",
    "seed round",
    "venture",
    "valuation",
    "investor",
    "investment",
    "m&a",
    "merger",
    "acquisition",
    "ipo",
    "round",
    "fundraise",
    "\u0440\u0430\u0443\u043d\u0434",
    "\u0438\u043d\u0432\u0435\u0441\u0442",
    "\u043e\u0446\u0435\u043d\u043a",
    "\u0441\u0434\u0435\u043b\u043a",
    "\u043f\u043e\u0433\u043b\u043e\u0449",
    "\u043f\u0440\u0438\u0432\u043b\u0435\u043a",
    "\u0432\u0435\u043d\u0447\u0443\u0440",
)
DRY_PROCESS_KEYWORDS = (
    "permit",
    "permitting",
    "approval",
    "approved",
    "compliance",
    "regulatory",
    "regulation",
    "zoning",
    "planning framework",
    "planning system",
    "document workflow",
    "document management",
    "paperwork",
    "standards",
    "standardization",
    "code check",
    "code compliance",
    "site selection",
    "feasibility analysis",
    "policy threshold",
    "forms and workflows",
)
MARKETING_EXPLAINER_KEYWORDS = (
    "/blog/",
    "ultimate guide",
    "complete guide",
    "guide for",
    "what is ",
    "how to ",
    "explained",
    "101",
)
DEPLOYMENT_EVIDENCE_KEYWORDS = (
    "deployed",
    "deployment",
    "rolled out",
    "rollout",
    "production site",
    "active site",
    "installed",
    "used on",
    "used by",
    "customer",
    "customers",
    "builders are using",
    "field deployment",
    "commercial sales",
)
INVALID_SOURCE_MARKERS = (
    "knowledge cutoff",
    "what i can offer instead",
    "honest answer",
    "\u043d\u0435 \u043c\u043e\u0433\u0443 \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u044d\u0442\u043e\u0442 \u0437\u0430\u043f\u0440\u043e\u0441",
    "\u043d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430 \u043a telegram",
    "\u043d\u0435 \u043c\u043e\u0433\u0443 \u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0432\u044b\u043c\u044b\u0448\u043b\u0435\u043d\u043d\u044b\u0435 \u043d\u043e\u0432\u043e\u0441\u0442\u0438",
    "\u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u0438 \u0447\u0435\u0441\u0442\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442",
)


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


def _load_editorial_policy() -> DescribeEditorialCallable:
    """Import editorial helpers in a way that works for package and script execution."""
    if __package__ in (None, ""):
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.editorial_policy import describe_editorial_fit
    else:
        from .editorial_policy import describe_editorial_fit

    return describe_editorial_fit


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


def _article_blob(article: dict[str, Any]) -> str:
    """Flatten the main searchable article fields into one lowercase string."""
    return " ".join(
        str(article.get(field, ""))
        for field in ("title", "text", "category_hint", "source_name", "url")
    ).lower()


def _article_lede_blob(article: dict[str, Any]) -> str:
    """Focus on metadata fields that usually define the main news angle."""
    return " ".join(
        str(article.get(field, ""))
        for field in ("title", "category_hint", "source_name", "url")
    ).lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    """Match short keywords strictly and longer ones as substrings."""
    normalized_keyword = keyword.lower()
    if len(normalized_keyword) <= 3 and normalized_keyword.isalpha():
        return re.search(rf"\b{re.escape(normalized_keyword)}\b", text) is not None
    return normalized_keyword in text


def _keyword_hits(text: str, keywords: Sequence[str]) -> set[str]:
    """Return the subset of keywords that matched in text."""
    return {
        keyword
        for keyword in keywords
        if _contains_keyword(text, keyword)
    }


def _has_high_interest_signal(article: dict[str, Any]) -> bool:
    """Approximate whether a story contains standout technical novelty."""
    return bool(_keyword_hits(_article_blob(article), HIGH_INTEREST_TECH_KEYWORDS))


def _has_deployment_evidence(article: dict[str, Any]) -> bool:
    """Check for signals that this is a deployment story, not an explainer page."""
    return bool(_keyword_hits(_article_blob(article), DEPLOYMENT_EVIDENCE_KEYWORDS))


def _is_business_noise(article: dict[str, Any]) -> bool:
    """Reject business-first stories even if they sprinkle in tech vocabulary."""
    return bool(_keyword_hits(_article_lede_blob(article), BUSINESS_NOISE_KEYWORDS))


def _is_dry_process_story(article: dict[str, Any]) -> bool:
    """Reject digitized paperwork/compliance stories unless there is standout tech."""
    dry_hits = _keyword_hits(_article_blob(article), DRY_PROCESS_KEYWORDS)
    if not dry_hits:
        return False
    return not _has_high_interest_signal(article)


def _is_marketing_explainer(article: dict[str, Any]) -> bool:
    """Reject vendor explainer content unless there is clear deployment evidence."""
    title_and_url = " ".join(
        str(article.get(field, ""))
        for field in ("title", "url", "source_name")
    ).lower()
    marketing_hits = _keyword_hits(title_and_url, MARKETING_EXPLAINER_KEYWORDS)
    if not marketing_hits:
        return False
    return not _has_deployment_evidence(article)


def _is_off_target_for_cio(article: dict[str, Any]) -> bool:
    """Reject stories that do not fit the CIO-style editorial radar."""
    if "editorial_score" not in article and "editorial_track_ids" not in article:
        return False
    editorial_score = int(article.get("editorial_score", 0) or 0)
    track_ids = article.get("editorial_track_ids", [])
    business_function_ids = article.get("business_function_ids", [])
    if not isinstance(track_ids, list) or not isinstance(business_function_ids, list):
        return editorial_score <= 0
    return editorial_score < 4 or not track_ids or not business_function_ids


def _editorial_rejection_reason(article: dict[str, Any]) -> str | None:
    """Return the editorial rejection reason for an article, if any."""
    text = _article_blob(article)
    if any(marker in text for marker in INVALID_SOURCE_MARKERS):
        return "invalid_source_content"
    if _is_business_noise(article):
        return "editorial_policy_non_technical_or_investment"
    if _is_dry_process_story(article) or _is_marketing_explainer(article):
        return "editorial_policy_boring_or_promotional"
    if _is_off_target_for_cio(article):
        return "editorial_policy_off_target_for_cio"
    return None


def _enrich_article_with_editorial_fit(
    article: dict[str, Any],
    describe_editorial_fit: DescribeEditorialCallable,
) -> dict[str, Any]:
    """Attach editorial fit metadata to an article without mutating the input."""
    fit = describe_editorial_fit(article)
    enriched_article = dict(article)
    enriched_article["editorial_score"] = int(fit.get("score", 0) or 0)
    enriched_article["editorial_track_ids"] = list(fit.get("track_ids", []))
    enriched_article["editorial_tracks"] = list(fit.get("track_labels", []))
    enriched_article["business_function_ids"] = list(fit.get("business_function_ids", []))
    enriched_article["business_functions"] = list(fit.get("business_functions", []))
    enriched_article["editorial_angle"] = str(fit.get("angle", "")).strip()
    return enriched_article


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
        "editorial_score": article.get("editorial_score"),
        "editorial_tracks": article.get("editorial_tracks", []),
        "business_functions": article.get("business_functions", []),
        "validation_errors": validation_errors or [],
        "rejection_reason": rejection_reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_existing_draft_records(drafts_date: str) -> list[dict[str, Any]]:
    """Load existing draft records for a date if the batch file already exists."""
    file_path = DRAFTS_DIR / f"{drafts_date}.json"
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as file_obj:
        loaded = json.load(file_obj)
    if not isinstance(loaded, list):
        raise ValueError("Drafts file must contain a list")
    return [record for record in loaded if isinstance(record, dict)]


def _selection_blocked_article_ids(records: Sequence[dict[str, Any]]) -> set[str]:
    """Return article IDs that should not consume new selection slots."""
    blocked_ids: set[str] = set()
    for record in records:
        article_id = str(record.get("article_id", "")).strip()
        if not article_id:
            continue
        status = str(record.get("status", "")).strip()
        if status in {"draft", "published", "skipped"} or bool(record.get("edited_by_admin")):
            blocked_ids.add(article_id)
    return blocked_ids


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
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Maximum number of drafts to generate (default: all eligible articles)",
    )
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

    try:
        existing_records = _load_existing_draft_records(articles_date)
    except Exception:
        logger.exception("Failed to load existing draft batch for %s", articles_date)
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
    editorial_rejected_records: list[dict[str, Any]] = []
    eligible_articles: list[dict[str, Any]] = []
    describe_editorial_fit = _load_editorial_policy()
    for article in source_backed_articles:
        enriched_article = _enrich_article_with_editorial_fit(article, describe_editorial_fit)
        rejection_reason = _editorial_rejection_reason(enriched_article)
        if rejection_reason:
            editorial_rejected_records.append(
                _build_draft_record(
                    enriched_article,
                    status="rejected",
                    rejection_reason=rejection_reason,
                )
            )
            continue
        eligible_articles.append(enriched_article)

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

    if editorial_rejected_records:
        logger.info(
            "Rejected %d low-signal or business-first articles due to editorial policy",
            len(editorial_rejected_records),
        )
    if eligible_articles:
        logger.info(
            "CIO-fit eligible articles: %d; top scores=%s",
            len(eligible_articles),
            ", ".join(
                str(article.get("editorial_score", 0))
                for article in sorted(
                    eligible_articles,
                    key=lambda item: int(item.get("editorial_score", 0) or 0),
                    reverse=True,
                )[:5]
            ),
        )

    blocked_article_ids = _selection_blocked_article_ids(existing_records)
    draftable_articles = [
        article
        for article in eligible_articles
        if str(article.get("id", "")).strip() not in blocked_article_ids
    ]
    if blocked_article_ids:
        logger.info(
            "Excluded %d already-queued or terminal article IDs from new selection slots",
            len(blocked_article_ids),
        )

    if not eligible_articles:
        logger.warning("No source-backed articles passed the editorial policy")
        all_rejected_records = rejected_records + editorial_rejected_records
        if all_rejected_records:
            draft_path = save_drafts(articles_date, all_rejected_records)
            logger.info(
                "Saved %d rejected records to %s",
                len(all_rejected_records),
                draft_path,
            )
            return ExitCode.PARTIAL_FAILURE
        return ExitCode.FAILURE

    if not draftable_articles:
        logger.info(
            "No new draftable articles remain after excluding existing draft/published/skipped items"
        )
        all_rejected_records = rejected_records + editorial_rejected_records
        if all_rejected_records:
            draft_path = save_drafts(articles_date, all_rejected_records)
            logger.info(
                "Saved %d rejected records to %s while keeping the existing queue intact",
                len(all_rejected_records),
                draft_path,
            )
        existing_draft_count = sum(
            str(record.get("status", "")).strip() == "draft"
            for record in existing_records
        )
        return ExitCode.SUCCESS if existing_draft_count else ExitCode.PARTIAL_FAILURE

    selected_articles = filter_articles(
        api_key,
        draftable_articles,
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

    all_records = draft_records + rejected_records + editorial_rejected_records
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
