#!/usr/bin/env python3
"""
Client for Perplexity API (sonar-deep-research).

Searches for PropTech news and parses the response into structured articles.
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(PROJECT_ROOT, "config", "prompt.md")

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


def _load_prompt() -> str:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _call_perplexity(api_key: str, prompt: str) -> dict:
    """Make API call to Perplexity. Returns raw JSON response."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar-deep-research",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты исследователь PropTech и ConTech. "
                    "Отвечай структурированно, каждая новость пронумерована, "
                    "с обязательной ссылкой."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "search_recency_filter": "week",
        "return_citations": True,
    }

    response = requests.post(
        PERPLEXITY_API_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def parse_perplexity_response(response_json: dict) -> list[dict]:
    """
    Parse Perplexity response into a list of article dicts.

    Splits text by numbered items (1., 2., ..., 10.).
    Maps citation references [1], [2] etc. to the citations array.
    Falls back to a single article if parsing fails.
    """
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        logger.error("Unexpected Perplexity response structure")
        return []

    citations = response_json.get("citations", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Split by numbered items: "1.", "2.", ... "10."
    # Pattern: line starts with a number followed by dot
    parts = re.split(r"\n(?=\d{1,2}\.[\s\)])", content)

    articles = []

    # If we got fewer than 3 parts, parsing likely failed — save as single article
    if len(parts) < 3:
        logger.warning(
            "Could not split into individual news items (got %d parts). "
            "Saving as single article.",
            len(parts),
        )
        articles.append({
            "id": str(uuid.uuid4()),
            "source_type": "perplexity",
            "source_name": "Perplexity Deep Research",
            "title": "PropTech Weekly Digest",
            "url": citations[0] if citations else "",
            "text": content,
            "image_url": None,
            "date": today,
            "category_hint": "digest",
            "collected_at": now_iso,
        })
        return articles

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract title: first meaningful line
        lines = part.split("\n")
        title_line = lines[0].strip()
        # Remove leading number and punctuation: "1. Title" -> "Title"
        title = re.sub(r"^\d{1,2}[\.\)]\s*", "", title_line)
        # Remove markdown bold
        title = re.sub(r"\*\*", "", title)
        title = title.strip()

        if not title:
            continue

        # Extract URLs from citation references [1], [2], etc.
        url = ""
        ref_matches = re.findall(r"\[(\d+)\]", part)
        for ref in ref_matches:
            idx = int(ref) - 1  # citations are 0-indexed
            if 0 <= idx < len(citations):
                url = citations[idx]
                break  # take the first relevant citation

        # Also check for direct URLs in text
        if not url:
            url_match = re.search(r"https?://[^\s\)]+", part)
            if url_match:
                url = url_match.group(0).rstrip(".,;)")

        # Try to guess category from keywords
        category_hint = _guess_category(part)

        articles.append({
            "id": str(uuid.uuid4()),
            "source_type": "perplexity",
            "source_name": _extract_company(title, part),
            "title": title[:200],
            "url": url,
            "text": part,
            "image_url": None,
            "date": today,
            "category_hint": category_hint,
            "collected_at": now_iso,
        })

    return articles


def _extract_company(title: str, text: str) -> str:
    """Try to extract company name from title or first sentence."""
    # Often the title starts with "Company Name — ..." or "Company Name:"
    for sep in ["—", "–", "-", ":", "("]:
        if sep in title:
            return title.split(sep)[0].strip()
    return "Perplexity"


CATEGORY_KEYWORDS = {
    "проектирование": ["BIM", "генеративный дизайн", "generative design", "feasibility", "планировк"],
    "визуализация": ["рендер", "render", "virtual staging", "3D-тур", "шоурум", "visualization"],
    "маркетинг": ["маркетинг", "marketing", "креатив", "таргетинг", "персонализац"],
    "продажи": ["CRM", "чат-бот", "chatbot", "лид", "lead", "продаж", "sales"],
    "ценообразование": ["AVM", "ценообразован", "pricing", "valuation", "оценк"],
    "роботы": ["робот", "robot", "3D-печать", "3D print", "модульн", "modular", "автоном"],
    "supply_chain": ["supply chain", "закупк", "procurement"],
    "smart_building": ["IoT", "digital twin", "цифровой двойник", "smart building", "предиктивн"],
    "платформы": ["ERP", "платформ", "интеграц", "ОС стройки"],
}


def _guess_category(text: str) -> str:
    """Guess article category based on keyword matching."""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return category
    return "unknown"


def search_proptech_news(api_key: str) -> list[dict]:
    """
    Main entry point: search for PropTech news via Perplexity.

    Returns a list of structured article dicts.
    """
    prompt = _load_prompt()
    logger.info("Calling Perplexity API (sonar-deep-research)...")

    response_json = _call_perplexity(api_key, prompt)
    articles = parse_perplexity_response(response_json)

    logger.info("Perplexity returned %d articles", len(articles))
    return articles
