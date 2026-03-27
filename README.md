# PropTech Pipeline

Telegram content pipeline for a PropTech / ConTech channel.

## What it does

- collects source material from Perplexity and YouTube
- filters out finance-first noise before generation
- generates Russian draft posts through OpenRouter
- lets a Telegram channel admin review, edit, skip, and publish drafts

## Editorial policy

- focus on technology, deployment, automation, tools, robotics, BIM, digital twins
- do not write about funding rounds, valuations, M&A, or generic business gossip
- generated posts should sound like human editorial notes, not like AI boilerplate
- drafts avoid first-person voice such as "I", "we", or "our"

## Main commands

```bash
pip install -r requirements.txt
python src/find_channels.py
python src/collect.py
python src/generate.py --max 5
python pipeline.py
python src/bot.py
python src/bot.py --once
```

## Data flow

- `src/collect.py` writes source-backed articles to `data/articles/YYYY-MM-DD.json`
- `src/generate.py` writes `draft|rejected|published|skipped` records to `data/drafts/YYYY-MM-DD.json`
- `src/bot.py` writes published records to `data/published/YYYY-MM-DD.json`
- `logs/` stores daily pipeline logs

## Configuration

Set variables in `config/.env` and never commit that file.

- `PERPLEXITY_API_KEY` for Perplexity collection
- `YOUTUBE_API_KEY` for YouTube collection
- `OPENROUTER_API_KEY` for draft generation
- `OPENROUTER_MODEL` optional model override, default `anthropic/claude-sonnet-4`
- `TG_BOT_TOKEN` for the review bot
- `TG_CHANNEL_ID` target channel username or numeric chat id
- `TG_ADMIN_ID` optional pinned Telegram user id; if omitted, the bot authorizes real channel administrators dynamically through Telegram `getChatMember`
- `PIPELINE_SCHEDULER_ENABLED` optional flag to let the same long-running bot service auto-run `collect -> generate`
- `PIPELINE_INTERVAL_MINUTES` optional scheduler cadence, default `180`
- `PIPELINE_RUN_ON_START` optional immediate run on boot, useful for Railway restarts

## Important limits

- `generate.py` fails fast without `OPENROUTER_API_KEY`
- `bot.py` fails fast without `TG_BOT_TOKEN` and `TG_CHANNEL_ID`
- YouTube transcript collection can still be affected by IP blocking
- Railway deployment in this repo is configured for the long-running review bot via `railway.json` with start command `python src/bot.py`
- If `PIPELINE_SCHEDULER_ENABLED=1`, the bot service also runs background `collect -> generate` jobs against the same mounted `/app/data` volume, which keeps drafts visible to the review UI without a second service
