#!/usr/bin/env python3
"""OpenRouter-backed client for article filtering and post generation."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Sequence
from typing import Any

import requests

from src.retry_utils import retry_call

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
OPENROUTER_TIMEOUT_SECONDS = 90
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
ALLOWED_CATEGORIES = (
    "PropTech",
    "ConTech",
    "\u0418\u043d\u0432\u0435\u0441\u0442\u0438\u0446\u0438\u0438",
    "\u0420\u0435\u0433\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
    "\u0422\u0440\u0435\u043d\u0434\u044b",
)
FIRST_PERSON_PATTERN = re.compile(
    r"\b(\u044f|\u043c\u044b|\u043c\u043d\u0435|\u043d\u0430\u043c|\u043d\u0430\u0441|"
    r"\u043d\u0430\u0448(?:[а-яё]+)?|"
    r"\u043c\u043e\u0439|\u043c\u043e\u044f|\u043c\u043e\u0438|\u043c\u043e\u0451|\u0443 \u043d\u0430\u0441)\b",
    flags=re.IGNORECASE,
)
STYLE_PROFILES = (
    (
        "sharp_newsroom",
        "Open with the concrete technical shift, not with a broad introduction. "
        "Use brisk, clean sentences and end on the operational consequence.",
    ),
    (
        "field_note",
        "Write like an editor who noticed a useful implementation detail in the wild. "
        "Make the middle paragraph practical and grounded.",
    ),
    (
        "product_zoom",
        "Center the post on what exactly changed in the product or workflow. "
        "Name the mechanism, not just the promise.",
    ),
    (
        "contrarian_lens",
        "Sound curious but unsentimental. "
        "Highlight one limitation, trade-off, or bottleneck instead of pure praise.",
    ),
)


class OpenRouterAPIError(RuntimeError):
    """OpenRouter API error that keeps the HTTP status for retry decisions."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_retryable(self) -> bool:
        """Whether retry/backoff should be attempted for this API error."""
        return self.status_code in RETRYABLE_STATUS_CODES


def _build_openrouter_headers(api_key: str) -> dict[str, str]:
    """Build HTTP headers for OpenRouter requests."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    referer = os.getenv("OPENROUTER_SITE_URL", "").strip()
    app_title = os.getenv("OPENROUTER_APP_NAME", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if app_title:
        headers["X-OpenRouter-Title"] = app_title
    return headers


def _extract_openrouter_text(response_payload: dict[str, Any]) -> str:
    """Extract assistant text from an OpenRouter chat completion response."""
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenRouter response does not contain choices")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("OpenRouter choice must be an object")

    error_payload = first_choice.get("error")
    if isinstance(error_payload, dict):
        raise OpenRouterAPIError(
            str(error_payload.get("message", "OpenRouter choice returned an error"))
        )

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenRouter choice is missing message object")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter message content is empty")

    return content.strip()


def _parse_json_payload(raw_text: str) -> dict[str, Any]:
    """Parse model output as JSON, tolerating fenced code blocks."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("Model response does not contain a JSON object")

    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Model response JSON must be an object")
    return payload


def _style_brief_for_article(article: dict[str, Any]) -> str:
    """Pick a deterministic writing brief so drafts do not sound templated."""
    seed = (
        str(article.get("id", "")).strip()
        or str(article.get("url", "")).strip()
        or str(article.get("title", "")).strip()
        or "default"
    )
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    profile_name, profile_brief = STYLE_PROFILES[int(digest, 16) % len(STYLE_PROFILES)]
    return f"Style profile `{profile_name}`: {profile_brief}"


def _call_claude_json(
    api_key: str,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    """Call OpenRouter and parse the model result as JSON."""

    def _request() -> dict[str, Any]:
        response = requests.post(
            OPENROUTER_API_URL,
            headers=_build_openrouter_headers(api_key),
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
            timeout=OPENROUTER_TIMEOUT_SECONDS,
        )

        try:
            response_payload = response.json()
        except ValueError:
            response_payload = None

        if response.status_code >= 400:
            error_message = f"OpenRouter request failed with status {response.status_code}"
            if isinstance(response_payload, dict):
                error = response_payload.get("error")
                if isinstance(error, dict) and error.get("message"):
                    error_message = str(error["message"])
            raise OpenRouterAPIError(
                error_message,
                status_code=response.status_code,
            )

        if not isinstance(response_payload, dict):
            raise ValueError("OpenRouter returned a non-object response body")

        return _parse_json_payload(_extract_openrouter_text(response_payload))

    return retry_call(
        _request,
        operation="OpenRouter JSON request",
        retry_exceptions=(requests.exceptions.RequestException, OpenRouterAPIError),
        should_retry=lambda exc: (
            isinstance(exc, requests.exceptions.RequestException)
            or (isinstance(exc, OpenRouterAPIError) and exc.is_retryable)
        ),
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
        "You are the editor of a Russian-language Telegram channel about "
        "PropTech and ConTech. Select only technology-driven stories for "
        "Russian-speaking real estate professionals. Prefer deployed tools, "
        "automation, AI workflows, robotics, BIM, digital twins, engineering "
        "methods, and operational product changes. Exclude funding rounds, "
        "M&A, partnerships without shipped tech, executive moves, and generic "
        "market commentary."
    )
    user_prompt = (
        "Return only a JSON object of the form "
        '{"selected_ids":["id1","id2"]}. '
        f"Select no more than {max_items} articles.\n\n"
        "Prioritize stories with concrete implementation details, measurable "
        "results, and product substance. Do not select items whose main news "
        "angle is investment, valuation, fundraising, or corporate finance.\n\n"
        f"Articles:\n{json.dumps(article_summaries, ensure_ascii=False, indent=2)}"
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
        logger.exception(
            "OpenRouter filtering failed; falling back to first %d articles",
            max_items,
        )
        return list(articles[:max_items])

    selected_id_set = {str(item).strip() for item in selected_ids if str(item).strip()}
    selected_articles = [
        article
        for article in articles
        if str(article.get("id", "")).strip() in selected_id_set
    ]
    if not selected_articles:
        logger.warning(
            "OpenRouter selected no valid article IDs; using first %d articles",
            max_items,
        )
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
        "You are the editor of a Russian-language Telegram channel about "
        "PropTech and ConTech. Write natural Russian that sounds like a human "
        "editor, not like a corporate AI assistant. Avoid first-person voice "
        "and never write from 'I', 'we', or 'our' perspective. Focus on "
        "technology, implementation details, constraints, and operational "
        "impact. Do not turn the post into a funding, PR, or business-roundup "
        "note. Avoid markdown. Return only a JSON object of the form "
        '{"text":"...","category":"..."} '
        f"where category is one of {', '.join(ALLOWED_CATEGORIES)}."
    )

    feedback_block = ""
    if feedback:
        feedback_block = "\nFix the previous issues:\n- " + "\n- ".join(feedback)

    style_brief = _style_brief_for_article(article)
    user_prompt = (
        "Write a Telegram post in Russian based on the article.\n"
        "Requirements:\n"
        "- 130-260 words, maximum 400\n"
        "- structure: concrete technical shift -> why it matters in practice -> limitation, trade-off, or next implication\n"
        "- write with a human rhythm; vary sentence length and avoid template phrasing\n"
        "- no first-person voice and no collective voice ('I', 'we', 'our')\n"
        "- no focus on investments, funding rounds, valuations, or deal gossip\n"
        "- optional emoji is allowed, but only if it feels natural and topic-relevant\n"
        "- no markdown (#, **, __)\n"
        f"- must end with the source URL: {article.get('url', '')}\n\n"
        f"{style_brief}\n\n"
        f"Article:\n{json.dumps(article, ensure_ascii=False, indent=2)}"
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
        raise ValueError("Model response is missing post text")
    if not category:
        raise ValueError("Model response is missing category")

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

    if FIRST_PERSON_PATTERN.search(post_text):
        errors.append("post contains first-person voice")

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
