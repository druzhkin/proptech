# PropTech Pipeline

Контент-пайплайн для Telegram-канала о PropTech.

Сейчас в репозитории реально реализованы:
- сбор контента через Perplexity и YouTube
- генерация черновиков через Claude
- единый entry point `python pipeline.py` для `collect -> generate`
- Telegram review/publish bot поверх `data/drafts`

Пока не реализованы полностью:
- полноценная end-to-end проверка live publish path в реальный канал
- автоматический запуск `bot.py` как managed service/daemon

## Быстрый старт

```bash
# Установить зависимости
pip install -r requirements.txt

# Заполнить API ключи
cp config/.env.example config/.env
# Отредактировать config/.env

# Найти YouTube channel IDs (одноразово)
python src/find_channels.py

# Собрать новости
python src/collect.py

# Сгенерировать черновики из собранных статей
python src/generate.py --max 5

# Полный текущий пайплайн
python pipeline.py

# Запустить review/publish bot
python src/bot.py
```

## Команды

| Команда | Описание |
|---------|----------|
| `python src/find_channels.py` | Поиск YouTube channel_id по названиям |
| `python src/collect.py` | Сбор из всех источников |
| `python src/collect.py --engine perplexity` | Только Perplexity |
| `python src/collect.py --engine youtube` | Только YouTube |
| `python src/generate.py --max 5` | Генерация до 5 черновиков из собранных статей |
| `python pipeline.py` | Последовательно запускает `collect -> generate` |
| `python src/bot.py` | Admin-only review/publish bot для `/drafts` и `/status` |
| `python src/bot.py --once` | Однократный poll-cycle для smoke/fail-fast проверки |

## Структура

```
config/     — конфигурация (ключи, каналы, промпты, evergreen topics)
src/        — код сбора, генерации и Telegram review bot
data/       — articles/, drafts/ и published/ по дням
logs/       — ежедневные pipeline-логи
```

## Источники

- **Perplexity API** (sonar-deep-research) — глубокий поиск новостей PropTech за неделю
- **YouTube Data API v3** — мониторинг каналов + транскрипты видео
- **Anthropic Claude API** — фильтрация статей и генерация Telegram-черновиков
- **Telegram Bot API** — admin review/publish flow через long polling

## Что создаётся на диске

- `data/articles/YYYY-MM-DD.json` — собранные статьи в unified schema
- `data/drafts/YYYY-MM-DD.json` — draft/rejected/published/skipped записи ревью-цикла
- `data/published/YYYY-MM-DD.json` — опубликованные записи с `telegram_message_id`
- `logs/pipeline-YYYY-MM-DD.log` — ежедневный лог для CLI-проходов

## Важные ограничения

- `generate.py` требует `ANTHROPIC_API_KEY`; без него скрипт fail-fast-ится понятной ошибкой
- `bot.py` требует `TG_BOT_TOKEN`, `TG_CHANNEL_ID`, `TG_ADMIN_ID`; без них бот не стартует
- evergreen fallback в `collect.py` сейчас создаёт placeholder-темы, а не source-backed статьи
- live publish в этом окружении пока не подтверждён реальными Telegram credentials
