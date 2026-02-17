#!/usr/bin/env python3
"""
Client for YouTube Data API v3 + youtube-transcript-api.

Functions:
- get_new_videos(youtube, channel_id, days_back=7) -> list[dict]
- get_transcript(video_id) -> str | None
- collect_all_channels(channels_config, youtube_api_key, days_back=7) -> list[dict]
"""

import httplib2
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

KEYWORDS = [
    "AI", "robot", "autonomous", "construction", "PropTech",
    "BIM", "digital twin", "generative design", "visualization",
    "smart building", "real estate tech", "modular", "3D print",
    "rendering", "virtual staging", "CRM", "pricing", "valuation",
    "computer vision", "IoT", "drone", "lidar", "prefab",
    "automation", "machine learning", "deep learning",
]


def get_new_videos(youtube, channel_id: str, days_back: int = 7) -> list[dict]:
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
        response = request.execute()
    except Exception as e:
        logger.error("Error fetching videos for channel %s: %s", channel_id, e)
        return []

    videos = []
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
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "ru"]
        )
        text = " ".join(t["text"] for t in transcript)

        # Skip garbage transcripts
        if len(text.split()) < 100:
            return None

        # Truncate to 5000 words
        words = text.split()[:5000]
        return " ".join(words)
    except Exception:
        logger.debug("No transcript for video %s", video_id)
        return None


def collect_all_channels(
    channels_config: dict,
    youtube_api_key: str,
    days_back: int = 7,
) -> list[dict]:
    """
    For each channel in config:
    1. Fetch new videos
    2. Try to get transcript for each
    3. Return list of articles in unified format
    """
    http = httplib2.Http(disable_ssl_certificate_validation=True)
    youtube = build("youtube", "v3", developerKey=youtube_api_key, http=http)
    articles = []

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
