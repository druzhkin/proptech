# PropTech Pipeline Notes

## Current scope

- `src/collect.py`: collect source material from Perplexity and YouTube
- `src/generate.py`: reject finance-first noise and generate Russian drafts via OpenRouter
- `src/bot.py`: admin review bot for `/drafts`, `/status`, Publish, Edit, Skip
- `pipeline.py`: run `collect -> generate`

## Editorial constraints

- the channel is about technology in development and construction
- funding rounds, valuations, and business-only stories should be rejected
- generated posts should feel human, concise, and varied
- posts must not use first-person voice

## Runtime expectations

- `OPENROUTER_API_KEY` is required for generation
- `TG_BOT_TOKEN` and `TG_CHANNEL_ID` are required for the bot
- `TG_ADMIN_ID` is optional; without it, the bot verifies whether the Telegram user is an actual admin of the configured channel

## Commands

```bash
python src/collect.py
python src/generate.py --max 5
python pipeline.py
python src/bot.py
python src/bot.py --once
ruff check src/ tests/ --fix
mypy src/ --ignore-missing-imports
pytest tests/ -v --tb=short
```
