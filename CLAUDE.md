# PropTech Pipeline

## Overview
Content pipeline for a Telegram channel about PropTech/ConTech.

Current implemented flow:
- `src/collect.py` — collects articles from Perplexity and YouTube
- `src/generate.py` — filters articles and writes draft/rejected records via Claude
- `pipeline.py` — runs `collect -> generate`
- `src/bot.py` — reviews drafts and publishes approved posts to Telegram

Still missing:
- live-verified Telegram publish path in the current environment
- background/service management for `bot.py`

## Architecture
- **config/** — API keys, channel lists, prompts, evergreen topics
- **src/** — collection, Claude generation, Telegram review bot, shared logging/retry helpers
- **data/** — collected articles, generated drafts, and published posts by date
- **logs/** — daily pipeline logs

## Tech Stack
- Python 3.10+
- Perplexity API (sonar-deep-research) — news search
- YouTube Data API v3 + youtube-transcript-api — video monitoring
- Anthropic Claude API — article selection + draft generation
- Telegram Bot API — admin review and channel publishing
- python-dotenv — env management

## Key Commands
```bash
# Install dependencies
pip install -r requirements.txt

# One-time: find YouTube channel IDs
python src/find_channels.py

# Collect news (all sources)
python src/collect.py

# Collect from specific engine
python src/collect.py --engine perplexity
python src/collect.py --engine youtube

# Generate drafts from collected articles
python src/generate.py --max 5

# Full currently implemented pipeline
python pipeline.py

# Review and publish drafts
python src/bot.py
python src/bot.py --once
```

## Data Format
All articles follow a unified schema:
```json
{
  "id": "uuid",
  "source_type": "perplexity|youtube",
  "source_name": "channel or source name",
  "title": "article title",
  "url": "source URL",
  "text": "full text or transcript",
  "image_url": "thumbnail URL or null",
  "date": "YYYY-MM-DD",
  "category_hint": "category from prompt or unknown",
  "collected_at": "ISO datetime"
}
```

Generated drafts are stored as JSON objects with at least:
```json
{
  "id": "uuid",
  "article_id": "source article id",
  "title": "article title",
  "url": "source URL or evergreen placeholder URL",
  "category": "PropTech|ConTech|Инвестиции|Регулирование|Тренды",
  "text": "generated Telegram text",
  "status": "draft|rejected|published|skipped",
  "validation_errors": [],
  "rejection_reason": "string | null",
  "created_at": "ISO datetime"
}
```

## Configuration
- **config/.env** — API keys (NEVER commit). Keys: `PERPLEXITY_API_KEY`, `YOUTUBE_API_KEY`, `ANTHROPIC_API_KEY`, `TG_BOT_TOKEN`, `TG_CHANNEL_ID`, `TG_ADMIN_ID`
- **config/channels.json** — YouTube channels with channel_id (run find_channels.py to populate)
- **config/prompt.md** — Perplexity search prompt (Russian, structured for PropTech news)
- **config/evergreen_topics.json** — Backup topic bank for slow news days

## Error Handling Philosophy
Never crash silently. Current rules:
- `collect.py` fail-fast checks required env vars
- external API calls use retry/backoff for transient failures
- empty Perplexity result can fall back to evergreen topics
- `generate.py` fail-fast checks `ANTHROPIC_API_KEY`
- evergreen placeholders are explicitly rejected at generation time instead of being treated as sourced articles
- `bot.py` fail-fast checks Telegram env vars and falls back to text-only publish if photo upload fails

## Code Style
- Type hints on function signatures
- Docstrings on public functions
- Logging via `logging` module, not print()
- Shared logging bootstrap writes to `logs/pipeline-YYYY-MM-DD.log`
- All file paths relative to project root
