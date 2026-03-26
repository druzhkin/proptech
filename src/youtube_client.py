#!/usr/bin/env python3
"""
Client for YouTube Data API v3 + youtube-transcript-api.

Functions:
- get_new_videos(youtube, channel_id, days_back=14) -> list[dict]
- get_transcript(video_id) -> str | None
- collect_all_channels(channels_config, youtube_api_key, days_back=14) -> list[dict]
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)

from src.retry_utils import retry_call

logger = logging.getLogger(__name__)

KEYWORDS = [
    "AI", "robot", "autonomous", "construction", "PropTech",
    "BIM", "digital twin", "generative design", "visualization",
    "smart building", "real estate tech", "modular", "3D print",
    "rendering", "virtual staging", "CRM", "pricing", "valuation",
    "computer vision", "IoT", "drone", "lidar", "prefab",
    "automation", "machine learning", "deep learning",
]
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
TRANSCRIPT_LANGUAGES = ("ru", "en")
TRANSCRIPT_MAX_WORDS = 5000
MIN_TRANSCRIPT_WORDS = 100


def _should_retry_http_error(exc: BaseException) -> bool:
    """Retry only transient YouTube API failures."""
    if isinstance(exc, HttpError):
        status_code = getattr(exc, "status_code", None)
        if status_code is None and getattr(exc, "resp", None) is not None:
            status_code = getattr(exc.resp, "status", None)
        return status_code in TRANSIENT_HTTP_STATUS_CODES
    return True


def _normalize_transcript(snippets: Iterable[Any]) -> str:
    """Collapse transcript snippets from old or new library APIs into plain text."""
    parts: list[str] = []
    for snippet in snippets:
        if isinstance(snippet, dict):
            text = str(snippet.get("text", "")).strip()
        else:
            text = str(getattr(snippet, "text", "")).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def get_new_videos(
    youtube: Any,
    channel_id: str,
    days_back: int = 14,
) -> list[dict[str, str]]:
    """Fetch recent videos from a channel, filtered by PropTech keywords."""
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).isoformat()

    try:
        request = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            publishedAfter=published_after,
            order="date",
            maxResults=10,
            type="video",
        )
        response = retry_call(
            request.execute,
            operation=f"YouTube search for channel {channel_id}",
            retry_exceptions=(HttpError, OSError, TimeoutError),
            should_retry=_should_retry_http_error,
            logger=logger,
        )
    except Exception as e:
        logger.error("Error fetching videos for channel %s: %s", channel_id, e)
        return []

    videos: list[dict[str, str]] = []
    for item in response.get("items", []):
        video_id = item["id"]["videoId"]
        snippet = item["snippet"]
        title = snippet["title"]
        description = snippet.get("description", "")

        # Filter by keywords
        text = (title + " " + description).lower()
        if not any(kw.lower() in text for kw in KEYWORDS):
            continue

        videos.append({
            "video_id": video_id,
            "title": title,
            "description": description,
            "published_at": snippet["publishedAt"],
            "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        })

    return videos


def get_transcript(video_id: str) -> str | None:
    """
    Get video transcript. Returns None if unavailable or too short.

    Truncates to 5000 words max.
    """
    try:
        transcript_api: Any = YouTubeTranscriptApi()
        fetch_method = getattr(transcript_api, "fetch", None)

        if callable(fetch_method):
            transcript = retry_call(
                lambda: fetch_method(video_id, languages=TRANSCRIPT_LANGUAGES),
                operation=f"YouTube transcript fetch for {video_id}",
                retry_exceptions=(YouTubeRequestFailed, RequestBlocked, IpBlocked),
                logger=logger,
            )
        else:
            legacy_method = getattr(YouTubeTranscriptApi, "get_transcript", None)
            if not callable(legacy_method):
                raise RuntimeError(
                    "youtube-transcript-api does not expose fetch/get_transcript"
                )
            transcript = retry_call(
                lambda: legacy_method(video_id, languages=list(TRANSCRIPT_LANGUAGES)),
                operation=f"YouTube transcript fetch for {video_id}",
                retry_exceptions=(YouTubeRequestFailed, RequestBlocked, IpBlocked),
                logger=logger,
            )

        text = _normalize_transcript(transcript)
        if len(text.split()) < MIN_TRANSCRIPT_WORDS:
            return None

        words = text.split()[:TRANSCRIPT_MAX_WORDS]
        return " ".join(words)
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
        logger.debug("Transcript unavailable for video %s: %s", video_id, exc)
        return None
    except Exception as exc:
        logger.warning("Failed to load transcript for video %s: %s", video_id, exc)
        return None


def collect_all_channels(
    channels_config: dict[str, list[dict[str, str]]],
    youtube_api_key: str,
    days_back: int = 14,
) -> list[dict[str, str | None]]:
    """
    For each channel in config:
    1. Fetch new videos
    2. Try to get transcript for each
    3. Return list of articles in unified format
    """
    youtube = build("youtube", "v3", developerKey=youtube_api_key)
    articles: list[dict[str, str | None]] = []

    for channel in channels_config["channels"]:
        if not channel.get("channel_id"):
            logger.debug("Skipping %s — no channel_id", channel["name"])
            continue

        logger.info("Checking channel: %s", channel["name"])
        videos = get_new_videos(youtube, channel["channel_id"], days_back)
        logger.info("  Found %d relevant videos", len(videos))

        for video in videos:
            transcript = get_transcript(video["video_id"])

            articles.append({
                "id": str(uuid.uuid4()),
                "source_type": "youtube",
                "source_name": channel["name"],
                "title": video["title"],
                "url": f"https://www.youtube.com/watch?v={video['video_id']}",
                "text": transcript or video["description"],
                "image_url": video["thumbnail"],
                "date": video["published_at"][:10],
                "category_hint": "unknown",
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    return articles
