from __future__ import annotations

from src import youtube_client


class _FakeSnippet:
    def __init__(self, text: str) -> None:
        self.text = text


def test_get_transcript_supports_fetch_api(monkeypatch) -> None:
    """The client should support youtube-transcript-api 1.x fetch()."""
    transcript_text = " ".join(["word"] * 120)

    class FakeTranscriptApi:
        def fetch(self, video_id: str, languages: tuple[str, str]):
            assert video_id == "video-1"
            assert languages == youtube_client.TRANSCRIPT_LANGUAGES
            return [_FakeSnippet(transcript_text)]

    monkeypatch.setattr(youtube_client, "YouTubeTranscriptApi", FakeTranscriptApi)

    transcript = youtube_client.get_transcript("video-1")

    assert transcript == transcript_text


def test_collect_all_channels_falls_back_to_description(monkeypatch) -> None:
    """Missing transcripts should degrade to the video description."""
    captured: dict[str, int] = {}

    monkeypatch.setattr(youtube_client, "build", lambda *args, **kwargs: object())

    def fake_get_new_videos(youtube, channel_id: str, days_back: int):
        captured["days_back"] = days_back
        assert channel_id == "channel-1"
        return [
            {
                "video_id": "video-1",
                "title": "AI construction update",
                "description": "fallback description",
                "published_at": "2026-03-26T08:00:00Z",
                "thumbnail": "https://img.youtube.com/vi/video-1/maxresdefault.jpg",
            }
        ]

    monkeypatch.setattr(youtube_client, "get_new_videos", fake_get_new_videos)
    monkeypatch.setattr(youtube_client, "get_transcript", lambda _video_id: None)

    articles = youtube_client.collect_all_channels(
        {"channels": [{"name": "Demo", "channel_id": "channel-1"}]},
        "youtube-key",
    )

    assert captured["days_back"] == 14
    assert len(articles) == 1
    assert articles[0]["text"] == "fallback description"
    assert articles[0]["source_name"] == "Demo"
