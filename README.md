# PropTech Pipeline

Контент-пайплайн для Telegram-канала о PropTech. Собирает новости через Perplexity API и мониторит YouTube-каналы.

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
```

## Команды

| Команда | Описание |
|---------|----------|
| `python src/find_channels.py` | Поиск YouTube channel_id по названиям |
| `python src/collect.py` | Сбор из всех источников |
| `python src/collect.py --engine perplexity` | Только Perplexity |
| `python src/collect.py --engine youtube` | Только YouTube |

## Структура

```
config/     — конфигурация (ключи, каналы, промпты)
src/        — скрипты сбора данных
data/       — собранные статьи (JSON по дням)
```

## Источники

- **Perplexity API** (sonar-deep-research) — глубокий поиск новостей PropTech за неделю
- **YouTube Data API v3** — мониторинг каналов + транскрипты видео
