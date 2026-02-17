# PropTech Pipeline

## Overview
Content pipeline for a Telegram channel about PropTech/ConTech. Collects news via Perplexity API (deep research) and monitors YouTube channels for relevant videos with transcripts.

## Architecture
- **config/** — API keys, channel lists, prompts, evergreen topics
- **src/** — Python scripts for data collection
- **data/** — Collected articles (JSON by date), drafts, published

## Tech Stack
- Python 3.10+
- Perplexity API (sonar-deep-research) — news search
- YouTube Data API v3 + youtube-transcript-api — video monitoring
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

## Configuration
- **config/.env** — API keys (NEVER commit). Keys: PERPLEXITY_API_KEY, YOUTUBE_API_KEY, ANTHROPIC_API_KEY, TG_BOT_TOKEN, TG_CHANNEL_ID, TG_ADMIN_ID
- **config/channels.json** — YouTube channels with channel_id (run find_channels.py to populate)
- **config/prompt.md** — Perplexity search prompt (Russian, structured for PropTech news)
- **config/evergreen_topics.json** — Backup topic bank for slow news days

## Error Handling Philosophy
Never crash. Log errors and continue with whatever data was collected. Each API source is independent — if Perplexity fails, YouTube still runs.

## Code Style
- Type hints on function signatures
- Docstrings on public functions
- Logging via `logging` module, not print()
- All file paths relative to project root
