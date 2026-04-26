# Аудит проекта PropTech Pipeline

Дата: 2026-04-26
Статус: повторный аудит после 13 завершённых итераций

---

## Объём проверки

- `specs/specs-requirements.md`
- `src/*.py` (13 файлов, ~4500 строк)
- `tests/*.py` (12 файлов, ~59 тестов)
- `config/*.json`, `config/prompt.md`, `config/.env.example`
- `README.md`, `AGENTS.md`, `CLAUDE.md`
- `pipeline.py`, `requirements.txt`

---

## Краткий вывод

Проект реализован end-to-end: сбор (R1), генерация (R2), Telegram-бот (R3), пайплайн/шедулер (R4), тесты (R5), документация (R6). Все требования спеки закрыты на уровне MVP.

Однако codebase накопил архитектурный технический долг: огромные файлы нарушают SRP, есть дублирование кода, не все edge cases покрыты тестами, graceful shutdown отсутствует. Quality gates зелёные, но масштабируемость страдает.

---

## Что подтверждено проверкой

- `ruff check src/ tests/ --fix` — ✅ без ошибок
- `mypy src/ --ignore-missing-imports` — ✅ без ошибок
- `pytest tests/ -v --tb=short` — ✅ 59 passed
- `python -c "from src.collect import main; print('collect OK')"` — ✅
- `python -c "from src.generate import main; print('generate OK')"` — ✅
- `python -c "from src.bot import main; print('bot OK')"` — ✅
- `python -c "import pipeline; print('pipeline OK')"` — ✅
- Live OpenRouter path подтверждён в итерации 6
- Live Telegram bot auth и publish path подтверждены в итерациях 7–8
- Railway deployment с in-process scheduler подтверждён в итерации 13

---

## Критические баги и блокеры

**P0 — отсутствуют.** Проект стабилен, работает в production.

---

## Архитектурные проблемы

### P1-1. Монолитные файлы нарушают SRP

- `src/bot.py` — 1004 строки. Смешаны: HTTP-клиент Telegram, UI-хендлеры, persistence-логика (JSON IO), business-логика review flow, шедулер-запуск.
- `src/generate.py` — 747 строки. Смешаны: editorial heuristic-фильтры, IO-логика (JSON merge/save), CLI-парсинг, draft-фабрика, интеграция с claude_client.

Последствия: сложно тестировать изолированно, изменения в одной зоне затрагивают всё, новым контрибьюторам сложно ориентироваться.

### P1-2. Дублирование кода между модулями

- `_article_blob()`, `_contains_keyword()`, `_keyword_hits()` — идентичные функции в `src/editorial_policy.py` и `src/generate.py`.
- `_should_retry_http_error()` — дублируется в `src/youtube_client.py` и `src/find_channels.py`.

Последствия: изменение keyword-matching логики требует редактирования двух файлов, риск рассинхронизации.

### P1-3. Множественные lazy-import через sys.path

Паттерн `_load_*()` с `sys.path.insert` + импорт внутри функции используется в `collect.py`, `generate.py`, `bot.py`, `find_channels.py`. Это workaround для запуска скриптов напрямую, усложняет статический анализ.

### P1-4. Нет graceful shutdown для scheduler

`PipelineScheduler` — daemon thread. При SIGINT в `bot.py` поток scheduler'а прерывается неконтролируемо. Нет `scheduler.stop()` в обработчике сигнала.

### P1-5. Perplexity fallback влияет на exit code некорректно

В `src/collect.py` при evergreen fallback `perplexity_ok = False`, хотя статьи в `all_articles` попали. Это может привести к `PARTIAL_FAILURE` (exit 1) даже при успешном fallback.

---

## Отсутствующие фичи из спеки (резидуальные риски)

### R1. Мелкие пробелы

- `parse_perplexity_response()` отбрасывает ответы с <3 частей — если Perplexity вернула 1–2 новости, они теряются.
- `image_url` от Perplexity всегда `None` — не извлекается из источников.
- `maxResults=10` на YouTube без пагинации — активные каналы могут пропускать релевантные видео.

### R2. Генерация

- `max_tokens=1400` и `temperature=0.2` в `claude_client.py` — хардкод, без конфигурации через env.
- `_parse_json_payload()` использует `re.search(r"\{.*\}", ...)` — при наличии нескольких JSON-объектов в тексте может схватить неверный.

### R3. Бот

- Нет тестов на inline callback-обработчики (Publish/Edit/Skip).
- Нет тестов на редактирование текста админом (`pending_edits`, сохранение правки).
- Нет тестов на успешную отправку фото (только fallback при ошибке).
- `authorized_users` — mutable global set.

### R4. Пайплайн

- `pipeline_runner.py` возвращает `int`, но сравнивается с `0` в `pipeline_scheduler.py` — несогласованность типов с `IntEnum` из collect/generate.

### R5. Тесты

- Покрытие editorial_matrix очень узкое: только 2 теста, не покрыты 5 из 6 tracks, boost_keywords, граничные score.
- Нет тестов на backoff timing в `retry_utils`.
- Нет тестов на `setup_logging` idempotency.

---

## Качество кода

### Плюсы

- Type hints присутствуют на всех публичных функциях.
- Логирование единообразное через `logging_utils.setup_logging`.
- Error handling внешних API включает retry/backoff.
- JSON-схемы articles/drafts/published стабильны и обратно совместимы.
- Editorial policy вынесена в отдельный модуль и конфиг.

### Минусы

- Большие tuple-константы (`TECH_SIGNAL_KEYWORDS`, `BUSINESS_NOISE_KEYWORDS` и т.д.) в `generate.py` — 100+ строк хардкода.
- `validate_post()` считает слова через `len(post_text.split())` — неточно для русского языка.
- `setup_logging()` вызывает `root_logger.handlers.clear()` — потенциальные проблемы при многократном вызове (например, в тестах).
- `bot.py` использует `data=payload` вместо `json=payload` для некоторых Telegram API-вызовов.

---

## Приоритеты исправлений

### P1

1. Убрать дублирование `_article_blob`, `_contains_keyword`, `_keyword_hits` — вынести в shared helper или использовать только `editorial_policy.py`.
2. Рефакторинг `bot.py` и `generate.py` на более мелкие модули (в рамках одного пакета, без breaking changes).
3. Добавить graceful shutdown для scheduler (SIGINT/SIGTERM handlers).
4. Исправить `perplexity_ok` при evergreen fallback — корректный exit code.
5. Расширить тестовое покрытие editorial policy и inline callback бота.

### P2

1. Убрать дублирование `_should_retry_http_error` в shared HTTP-utility.
2. Улучшить `_parse_json_payload` — robust JSON extraction вместо regex.
3. Добавить jitter в `retry_utils.backoff`.
4. Сделать `max_tokens`/`temperature` конфигурируемыми через env.
5. Перейти от сырых `dict` к `TypedDict` или `dataclass` для Article/Draft.

---

## Итоговая оценка

Проект — рабочий production-MVP с end-to-end пайплайном. Все P0-блокеры закрыты. Основной риск сейчас — архитектурная энтропия: рост файлов и дублирование кода замедлят дальнейшую разработку. Следующие итерации должны фокусироваться на рефакторинге и расширении тестового покрытия, а не на новых фичах.
