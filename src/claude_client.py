#!/usr/bin/env python3
"""Anthropic Claude client for article filtering and post generation."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

import anthropic

from src.retry_utils import retry_call

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"
ALLOWED_CATEGORIES = (
    "PropTech",
    "ConTech",
    "Инвестиции",
    "Регулирование",
    "Тренды",
)

TRANSIENT_ANTHROPIC_EXCEPTIONS = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.APIResponseValidationError,
    anthropic.InternalServerError,
    anthropic.RateLimitError,
)


def _extract_text(message: anthropic.types.Message) -> str:
    """Extract concatenated text blocks from a Claude response."""
    parts: list[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_json_payload(raw_text: str) -> dict[str, Any]:
    """Parse Claude output as JSON, tolerating fenced code blocks."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("Claude response does not contain a JSON object")

    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Claude response JSON must be an object")
    return payload


def _call_claude_json(
    api_key: str,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    """Call Claude and parse the result as JSON."""
    client = anthropic.Anthropic(api_key=api_key)

    def _request() -> dict[str, Any]:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.2,
        )
        return _parse_json_payload(_extract_text(response))

    return retry_call(
        _request,
        operation="Claude JSON request",
        retry_exceptions=TRANSIENT_ANTHROPIC_EXCEPTIONS,
        logger=logger,
    )


def filter_articles(
    api_key: str,
    articles: Sequence[dict[str, Any]],
    *,
    max_items: int = 5,
    model: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    """Select the most relevant articles for draft generation."""
    if not articles:
        return []

    article_summaries = [
        {
            "id": article["id"],
            "title": article.get("title", ""),
            "source_name": article.get("source_name", ""),
            "category_hint": article.get("category_hint", ""),
            "url": article.get("url", ""),
            "text_excerpt": str(article.get("text", ""))[:1200],
        }
        for article in articles
    ]

    system_prompt = (
        "Ты редактор Telegram-канала о PropTech/ConTech. "
        "Выбирай самые ценные статьи для русскоязычной аудитории девелоперов: "
        "новизна, практическая ценность, значимость для рынка, отсутствие рекламного шума."
    )
    user_prompt = (
        "Верни только JSON-объект вида "
        '{"selected_ids":["id1","id2"]}. '
        f"Нужно выбрать не больше {max_items} материалов.\n\n"
        f"Статьи:\n{json.dumps(article_summaries, ensure_ascii=False, indent=2)}"
    )

    try:
        payload = _call_claude_json(
            api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_tokens=600,
        )
        selected_ids = payload.get("selected_ids", [])
        if not isinstance(selected_ids, list):
            raise ValueError("selected_ids must be a list")
    except Exception:
        logger.exception("Claude filtering failed; falling back to first %d articles", max_items)
        return list(articles[:max_items])

    selected_id_set = {
        str(item).strip()
        for item in selected_ids
        if str(item).strip()
    }
    selected_articles = [
        article
        for article in articles
        if str(article.get("id", "")).strip() in selected_id_set
    ]
    if not selected_articles:
        logger.warning("Claude selected no valid article IDs; using first %d articles", max_items)
        return list(articles[:max_items])

    return selected_articles[:max_items]


def generate_post(
    api_key: str,
    article: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    feedback: Sequence[str] | None = None,
) -> dict[str, str]:
    """Generate a Telegram post draft and category for a single article."""
    system_prompt = (
        "Ты редактор русскоязычного Telegram-канала о PropTech/ConTech. "
        "Пиши делово, конкретно, без воды, без markdown. "
        "Верни только JSON-объект вида "
        '{"text":"...","category":"..."} '
        f"где category одна из {', '.join(ALLOWED_CATEGORIES)}."
    )

    feedback_block = ""
    if feedback:
        feedback_block = "\nИсправь прошлые ошибки:\n- " + "\n- ".join(feedback)

    user_prompt = (
        "Сделай пост для Telegram на основе статьи.\n"
        "Требования:\n"
        "- 150-300 слов, максимум 400\n"
        "- структура: факт/событие -> почему важно -> что это значит для рынка\n"
        "- 1-2 тематических эмодзи в начале\n"
        "- без markdown (#, **, __)\n"
        f"- в конце обязательно ссылка на источник: {article.get('url', '')}\n\n"
        f"Статья:\n{json.dumps(article, ensure_ascii=False, indent=2)}"
        f"{feedback_block}"
    )

    payload = _call_claude_json(
        api_key,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        max_tokens=1400,
    )

    text = str(payload.get("text", "")).strip()
    category = str(payload.get("category", "")).strip()
    if not text:
        raise ValueError("Claude response is missing post text")
    if not category:
        raise ValueError("Claude response is missing category")

    return {"text": text, "category": category}


def validate_post(post_text: str, source_url: str) -> list[str]:
    """Validate a generated Telegram post against the R2 requirements."""
    errors: list[str] = []
    word_count = len(post_text.split())
    if word_count > 400:
        errors.append("post exceeds 400 words")

    if source_url and source_url not in post_text:
        errors.append("post is missing the source URL")

    if any(marker in post_text for marker in ("#", "**", "__")):
        errors.append("post contains markdown formatting")

    return errors


def generate_validated_post(
    api_key: str,
    article: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    max_regenerations: int = 1,
) -> tuple[dict[str, str], list[str]]:
    """Generate a post draft and retry once if validation fails."""
    feedback: list[str] = []
    attempts = max_regenerations + 1
    last_result: dict[str, str] = {"text": "", "category": ""}
    last_errors: list[str] = []

    for _attempt in range(attempts):
        last_result = generate_post(
            api_key,
            article,
            model=model,
            feedback=feedback,
        )
        last_errors = validate_post(
            last_result["text"],
            str(article.get("url", "")),
        )
        if last_result["category"] not in ALLOWED_CATEGORIES:
            last_errors.append("post category is invalid")
        if not last_errors:
            return last_result, []
        feedback = last_errors

    return last_result, last_errors
