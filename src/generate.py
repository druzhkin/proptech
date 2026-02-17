#!/usr/bin/env python3
"""
Post generation script. Filters top articles via Claude, then generates drafts.

Usage:
    python src/generate.py                        # Latest file from data/articles/
    python src/generate.py --date 2026-02-17      # Specific date
    python src/generate.py --file path/to/articles.json  # Specific file

Output: data/drafts/YYYY-MM-DD.json
"""

import argparse
import json
import logging
import os
import re
import sys
import uuid
from datetime import date, datetime, timezone

from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.claude_client import filter_articles, generate_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(PROJECT_ROOT, "config", ".env")
ARTICLES_DIR = os.path.join(PROJECT_ROOT, "data", "articles")
DRAFTS_DIR = os.path.join(PROJECT_ROOT, "data", "drafts")


def find_latest_articles() -> str | None:
    """Find the most recent articles file by date in filename."""
    if not os.path.isdir(ARTICLES_DIR):
        return None
    files = sorted(
        [f for f in os.listdir(ARTICLES_DIR) if f.endswith(".json")],
        reverse=True,
    )
    return os.path.join(ARTICLES_DIR, files[0]) if files else None


def load_json(path: str) -> list[dict]:
    """Load articles from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list[dict], path: str) -> None:
    """Save data to a JSON file, creating directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def validate_draft(draft: dict) -> list[str]:
    """Check draft against rules. Return list of warnings."""
    warnings = []
    text = draft["post_text"]
    word_count = draft["word_count"]

    # Length
    if word_count < 150:
        warnings.append(f"слишком короткий ({word_count} слов, мин 200)")
    if word_count > 600:
        warnings.append(f"слишком длинный ({word_count} слов, макс 500)")

    # Forbidden words
    forbidden = [
        "уникальн", "эксклюзивн", "не имеет аналогов",
        "революционн", "инновационн", "передовой",
        "а в России", "на российском рынке", "у нас пока",
    ]
    text_lower = text.lower()
    for word in forbidden:
        if word.lower() in text_lower:
            warnings.append(f"запрещённое слово: '{word}'")

    # Structure
    if "\U0001f4cc" not in text:  # 📌
        warnings.append("нет хука (📌)")
    if "Источник:" not in text and "источник:" not in text.lower() and "\U0001f3a5" not in text:
        warnings.append("нет ссылки на источник")
    if "#PropTech" not in text and "#proptech" not in text.lower():
        warnings.append("нет тега #PropTech")

    # Forbidden emoji (everything except allowed)
    allowed_emoji = set("\U0001f4cc\U0001f4ca\U0001f4a1\U0001f916\U0001f3a5")  # 📌📊💡🤖🎥
    found_emoji = set(re.findall(r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF]", text))
    bad_emoji = found_emoji - allowed_emoji
    if bad_emoji:
        warnings.append(f"запрещённые эмодзи: {''.join(bad_emoji)}")

    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Telegram post drafts")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date of articles file (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to specific articles JSON file",
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    # Determine articles path
    if args.file:
        articles_path = args.file
    elif args.date:
        articles_path = os.path.join(ARTICLES_DIR, f"{args.date}.json")
    else:
        articles_path = find_latest_articles()

    if not articles_path or not os.path.exists(articles_path):
        logger.error("No articles file found")
        return

    logger.info("Using articles from %s", articles_path)

    # 1. Load articles
    articles = load_json(articles_path)
    if not articles:
        logger.warning("No articles to process")
        return

    # 2. Filter: Claude picks top 5
    logger.info("Filtering %d articles...", len(articles))
    try:
        selected = filter_articles(articles, max_select=5)
    except Exception as e:
        logger.error("filter_articles failed: %s — retrying once", e)
        try:
            selected = filter_articles(articles, max_select=5)
        except Exception as e2:
            logger.error("filter_articles retry failed: %s — using all articles", e2)
            selected = [{"id": a["id"], "reason": "fallback: filter unavailable"} for a in articles[:5]]

    logger.info("Selected: %d articles", len(selected))
    for s in selected:
        logger.info("  - %s... — %s", s["id"][:8], s["reason"])

    # 3. Match full articles by id
    articles_by_id = {a["id"]: a for a in articles}
    selected_articles = [
        articles_by_id[s["id"]]
        for s in selected
        if s["id"] in articles_by_id
    ]

    if not selected_articles:
        logger.warning("No matching articles found after filtering")
        return

    # 4. Generate posts
    drafts = []
    for i, article in enumerate(selected_articles):
        logger.info(
            "Generating post %d/%d: %s...",
            i + 1, len(selected_articles), article["title"][:60],
        )
        try:
            post_text = generate_post(article)
        except Exception as e:
            logger.error("generate_post failed for '%s': %s", article["title"][:40], e)
            continue

        draft = {
            "id": str(uuid.uuid4()),
            "source_article_id": article["id"],
            "post_text": post_text,
            "image_url": article.get("image_url"),
            "source_url": article["url"],
            "source_name": article["source_name"],
            "category": article.get("category_hint", "unknown"),
            "content_type": "youtube_review" if article["source_type"] == "youtube" else "news",
            "scheduled_date": date.today().isoformat(),
            "status": "draft",
            "word_count": len(post_text.split()),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        drafts.append(draft)

    if not drafts:
        logger.warning("No drafts generated")
        return

    # 5. Validate
    for d in drafts:
        warnings = validate_draft(d)
        if warnings:
            logger.warning("Draft %s: %s", d["id"][:8], ", ".join(warnings))

    # 6. Save
    output_path = os.path.join(DRAFTS_DIR, f"{date.today().isoformat()}.json")
    save_json(drafts, output_path)
    logger.info("Saved %d drafts to %s", len(drafts), output_path)

    # 7. Preview
    for i, d in enumerate(drafts):
        print(f"\n{'=' * 60}")
        print(f"DRAFT {i + 1} ({d['word_count']} words)")
        print(f"{'=' * 60}")
        print(d["post_text"][:500])
        if len(d["post_text"]) > 500:
            print("...")


if __name__ == "__main__":
    main()
