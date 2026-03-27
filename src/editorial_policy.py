#!/usr/bin/env python3
"""Editorial policy helpers for CIO-oriented content selection."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EDITORIAL_MATRIX_PATH = PROJECT_ROOT / "config" / "editorial_matrix.json"

TRACK_ANGLE_HINTS = {
    "ai_knowledge_ops": (
        "Frame it as a practical AI workflow: what it automates, which internal "
        "documents or knowledge it touches, and what a low-risk pilot would look like."
    ),
    "open_source_tooling": (
        "Treat it like a tool radar item: what can be self-hosted or integrated, "
        "which team could pilot it, and what the setup trade-off is."
    ),
    "site_intelligence": (
        "Focus on the field mechanism: capture, robotics, inspection, or computer "
        "vision, plus what it changes on an active site."
    ),
    "bim_and_digital_twin": (
        "Explain the data layer, interoperability, or model workflow that changed, "
        "and why that matters beyond a demo."
    ),
    "sales_and_finance_automation": (
        "Make it concrete for sales or finance operations: which repetitive step gets "
        "faster, cleaner, or more visible."
    ),
    "smart_building_ops": (
        "Anchor the story in building operations: sensors, maintenance, energy, "
        "or fault detection, not in generic smart-city rhetoric."
    ),
}


@lru_cache(maxsize=1)
def load_editorial_matrix() -> dict[str, Any]:
    """Load the editorial matrix from disk."""
    with EDITORIAL_MATRIX_PATH.open("r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("editorial_matrix.json must contain an object")
    return data


def _article_blob(article: dict[str, Any]) -> str:
    """Flatten the main searchable article fields into one lowercase string."""
    return " ".join(
        str(article.get(field, ""))
        for field in ("title", "text", "category_hint", "source_name", "url")
    ).lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    """Match short keywords strictly and longer ones as substrings."""
    normalized_keyword = keyword.lower()
    if len(normalized_keyword) <= 3 and normalized_keyword.isalpha():
        return re.search(rf"\b{re.escape(normalized_keyword)}\b", text) is not None
    return normalized_keyword in text


def _keyword_hits(text: str, keywords: list[str]) -> set[str]:
    """Return the subset of keywords that matched in text."""
    return {
        keyword
        for keyword in keywords
        if _contains_keyword(text, keyword)
    }


def describe_editorial_fit(article: dict[str, Any]) -> dict[str, Any]:
    """Describe why an article does or does not fit the CIO content radar."""
    matrix = load_editorial_matrix()
    text = _article_blob(article)

    business_functions = matrix.get("business_functions", {})
    tracks = matrix.get("tracks", [])
    boost_keywords = matrix.get("boost_keywords", {})

    matched_track_rows: list[tuple[int, str, str, set[str], list[str]]] = []
    function_ids: set[str] = set()
    score = 0

    for raw_track in tracks:
        if not isinstance(raw_track, dict):
            continue
        track_id = str(raw_track.get("id", "")).strip()
        label = str(raw_track.get("label", "")).strip() or track_id
        keywords = [
            str(keyword).strip()
            for keyword in raw_track.get("keywords", [])
            if str(keyword).strip()
        ]
        track_hits = _keyword_hits(text, keywords)
        if not track_hits:
            continue

        linked_functions = [
            str(function_id).strip()
            for function_id in raw_track.get("business_functions", [])
            if str(function_id).strip()
        ]
        function_ids.update(linked_functions)
        track_score = 3 + min(len(track_hits), 3)
        matched_track_rows.append((track_score, track_id, label, track_hits, linked_functions))
        score += track_score

    for function_id, raw_meta in business_functions.items():
        if not isinstance(raw_meta, dict):
            continue
        keywords = [
            str(keyword).strip()
            for keyword in raw_meta.get("keywords", [])
            if str(keyword).strip()
        ]
        if _keyword_hits(text, keywords):
            function_ids.add(str(function_id))
            score += 1

    deployment_hits = _keyword_hits(
        text,
        [
            str(keyword).strip()
            for keyword in boost_keywords.get("deployment", [])
            if str(keyword).strip()
        ],
    )
    wow_hits = _keyword_hits(
        text,
        [
            str(keyword).strip()
            for keyword in boost_keywords.get("wow_factor", [])
            if str(keyword).strip()
        ],
    )
    score += min(len(deployment_hits), 2)
    score += min(len(wow_hits), 2)

    matched_track_rows.sort(key=lambda item: (-item[0], item[1]))
    track_ids = [track_id for _score, track_id, _label, _hits, _functions in matched_track_rows]
    track_labels = [label for _score, _track_id, label, _hits, _functions in matched_track_rows]
    business_function_ids = sorted(function_ids)
    business_function_labels = [
        str(business_functions[function_id].get("label", function_id))
        for function_id in business_function_ids
        if function_id in business_functions
    ]

    primary_track_id = track_ids[0] if track_ids else ""
    angle = TRACK_ANGLE_HINTS.get(
        primary_track_id,
        (
            "Focus on what could actually be piloted inside a developer company, "
            "who would own it, and what the implementation constraint is."
        ),
    )

    return {
        "score": score,
        "track_ids": track_ids,
        "track_labels": track_labels,
        "business_function_ids": business_function_ids,
        "business_functions": business_function_labels,
        "deployment_hits": sorted(deployment_hits),
        "wow_hits": sorted(wow_hits),
        "angle": angle,
    }
