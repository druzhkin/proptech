# План итераций

## Итерация 1 — 2026-03-26

### Цель итерации

Стабилизировать `R1` так, чтобы сборщик не деградировал молча, безопасно ходил во внешние API и имел минимальный тестовый контур.

### Задачи

- [x] TASK-1: Добавить общий bootstrap для `collect.py`: проверка обязательных env-переменных, понятные ошибки старта и корректные exit codes для full/partial failure — агент: Coder
- [x] TASK-2: Исправить клиентов внешних API: убрать отключение TLS-проверки, добавить retry/backoff, починить совместимость с `youtube-transcript-api>=1.x`, привести YouTube-сбор к окну в 14 дней — агент: Coder
- [x] TASK-3: Написать минимальный `pytest`-набор для критических сценариев `R1`: `deduplicate`, парсинг Perplexity, деградация transcript -> description, отказ при missing env — агент: Tester
- [x] TASK-4: Довести quality gates до зелёного состояния для текущего охвата `R1`: `ruff check src/ --fix`, `mypy src/ --ignore-missing-imports`, smoke import `src.collect` — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для нового набора тестов
- [x] smoke-тест: `python -c "from src.collect import main; print('collect OK')"`

### Замечания по объёму

- `R2` и `R3` осознанно не входят в итерацию 1: сначала нужно убрать P0-блокеры в `R1`
- fallback на `evergreen_topics.json`, `pipeline.py` и файловое логирование переносятся в следующую итерацию как `P1`

### Лог работ

- [CODE] `src/collect.py`: введены fail-fast проверки env, коды выхода `0/1/2`, lazy import источников и более предсказуемый summary по источникам
- [CODE] `src/perplexity_client.py`, `src/youtube_client.py`, `src/find_channels.py`, `src/retry_utils.py`: добавлены retry/backoff, убран insecure TLS bypass, починена совместимость с `youtube-transcript-api 1.x`, YouTube-сбор переведён на окно в 14 дней
- [TEST] `tests/test_collect.py`, `tests/test_perplexity_client.py`, `tests/test_retry_utils.py`, `tests/test_youtube_client.py`, `tests/conftest.py`: добавлены регрессионные тесты на fail-fast, парсинг, retry и transcript fallback
- [CRITIC] Прогнаны quality gates: `ruff check src/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.collect import main; print('collect OK')"`
- [COMMIT] Ветка `codex/iteration-1` запушена на `origin`, PR открыт: `https://github.com/druzhkin/proptech/pull/1`

### Ретроспектива итерации 1

- Не сломал базовый import-path для `collect.py`: smoke import зелёный, а запуск `python src/collect.py` остаётся совместимым за счёт lazy import источников
- Основные edge cases этой итерации закрыты: missing env теперь не маскируется, временные сетевые ошибки получают retry, отсутствие транскрипта деградирует в description
- Требования `R1/P0` закрыты частично, но по существу: fail-fast env, retry/backoff, совместимость с transcript API и тестовый контур готовы; fallback на `evergreen_topics.json` остаётся в `P1`
- Утечек credentials не добавлено: TLS bypass убран, ключи продолжают читаться только из `config/.env`
- Residual risk: парсер Perplexity всё ещё иногда сваливается в единый digest при нестандартной разметке ответа; это уже не P0 по надёжности запуска, но ещё не закрывает качество контента до конца

## Итерация 2 — 2026-03-26

### Цель итерации

Закрыть следующий слой надёжности в `R1/R4`: добавить эксплуатационное логирование и fallback на evergreen-темы, не делая преждевременный `pipeline.py`.

### Задачи

- [x] TASK-1: Вынести общее logging bootstrap в отдельный util: stdout + `logs/pipeline-YYYY-MM-DD.log`, формат по спеке, очистка логов старше 30 дней, интеграция в существующие CLI-скрипты — агент: Coder
- [x] TASK-2: Добавить fallback на `config/evergreen_topics.json` в `collect.py`, но только для сценария "Perplexity отработал без ошибок, но не вернул новостей", чтобы не маскировать реальные source failures — агент: Coder
- [x] TASK-3: Расширить `pytest`-набор сценариями на evergreen fallback и logging rotation/file creation — агент: Tester
- [x] TASK-4: Прогнать quality gates и обновить журнал итерации с остаточными рисками — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для нового набора тестов
- [x] smoke-тест: `python -c "from src.collect import main; print('collect OK')"`
- [x] manual-check: существующие CLI-скрипты пишут логи в `logs/pipeline-YYYY-MM-DD.log`

### Замечания по объёму

- `pipeline.py` сознательно не включён: делать общий entry point до появления `generate.py` и `bot.py` было бы архитектурно нечестно
- `R2` и `R3` всё ещё вне объёма этой итерации

### Лог работ

- [CODE] `src/logging_utils.py`, `src/collect.py`, `src/find_channels.py`: добавлен общий logging bootstrap с daily log file и очисткой логов старше 30 дней; существующие CLI начали писать в `logs/pipeline-YYYY-MM-DD.log`
- [CODE] `src/collect.py`: добавлен evergreen fallback только на сценарий пустого ответа Perplexity без source failure; evergreen-элементы получают внутренний `evergreen://...` URL для стабильной дедупликации
- [TEST] `tests/test_collect.py`, `tests/test_logging_utils.py`: добавлены сценарии на evergreen fallback, запрет маскировки source failure и ротацию/создание log file
- [CRITIC] Прогнаны quality gates: `ruff check src/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.collect import main; print('collect OK')"`, `python src/find_channels.py`
- [COMMIT] Ветка `codex/iteration-1` обновлена на `origin`, открытый PR `https://github.com/druzhkin/proptech/pull/1` содержит и итерацию 2

### Ретроспектива итерации 2

- Логирование стало эксплуатационным, а не только консольным: есть единый формат, файл за день и очистка старых логов
- Evergreen fallback теперь закрывает сценарий "новостей нет", но не скрывает реальное падение Perplexity как успешный сбор
- `pipeline.py` по-прежнему не сделан намеренно: общий entry point до появления `generate.py` и `bot.py` был бы вводящим в заблуждение слоем
- Утечек credentials не добавлено; логирование не пишет значения env-переменных
- Residual risk: evergreen fallback сейчас создаёт topic placeholders с `evergreen://...` вместо внешнего источника, и это придётся отдельно учесть, когда появится `generate.py` и строгая валидация ссылок

## Итерация 3 — 2026-03-26

### Цель итерации

Сделать первый рабочий thin slice `R2`: от чтения собранных статей до записи `data/drafts/YYYY-MM-DD.json` с фильтрацией, генерацией и базовой валидацией через Claude.

### Задачи

- [x] TASK-1: Реализовать `src/claude_client.py` с Anthropic SDK: выбор top-N статей, генерация поста, базовая валидация и retry/backoff для Claude API — агент: Coder
- [x] TASK-2: Реализовать `src/generate.py`: загрузка сегодняшних или последних доступных статей, вызов Claude-клиента, запись draft/rejected статусов в `data/drafts/YYYY-MM-DD.json`, интеграция с общим logging bootstrap — агент: Coder
- [x] TASK-3: Явно обработать evergreen placeholder-ы в генерации: не маскировать их под source-backed посты, а сохранять как `rejected` с понятной причиной — агент: Coder
- [x] TASK-4: Добавить `pytest`-покрытие для Claude JSON parsing, post validation и end-to-end generate flow на моках — агент: Tester
- [x] TASK-5: Прогнать quality gates и обновить журнал итерации с остаточными рисками — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для нового набора тестов
- [x] smoke-тест: `python -c "from src.generate import main; print('generate OK')"`
- [x] manual-check: `python src/generate.py --max 5` создаёт `data/drafts/YYYY-MM-DD.json` или даёт понятный fail-fast/rejected output

### Замечания по объёму

- `bot.py` и review flow всё ещё вне объёма этой итерации
- evergreen placeholder-ы не будут притворяться “обычными статьями со ссылкой”; для них нужен честный rejected path

### Лог работ

- [CODE] `src/claude_client.py`: добавлен Anthropic client wrapper с retry/backoff, JSON parsing, выбором top-N статей, генерацией поста и базовой валидацией
- [CODE] `src/generate.py`: добавлен первый рабочий R2-flow от чтения `data/articles` до записи `data/drafts`, с fallback на последний доступный день и merge-логикой, которая не затирает `published` записи при rerun
- [CODE] evergreen placeholder-ы теперь явно идут в `rejected` c причиной `evergreen_placeholder_requires_source_link`, а не превращаются в псевдо-sourced draft
- [TEST] `tests/test_claude_client.py`, `tests/test_generate.py`: добавлены тесты на Claude JSON parsing, fallback селекции, validate_post, latest-file loading, preserve-published merge и end-to-end generate flow на моках
- [CRITIC] Прогнаны quality gates: `ruff check src/ tests/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.generate import main; print('generate OK')"`, `python src/generate.py --max 5`
- [COMMIT] Ветка `codex/iteration-1` обновлена на `origin`, открытый PR `https://github.com/druzhkin/proptech/pull/1` содержит и итерацию 3

### Ретроспектива итерации 3

- `R2` больше не абстракция: в репозитории есть реальный `claude_client.py` и `generate.py`, которые можно вызывать как CLI
- Evergreen placeholder-ы обработаны честно: rejected path явный, а не спрятанный в “успешную” генерацию без настоящего источника
- Merge-логика в `data/drafts` не затирает уже опубликованные записи, что снижает риск следующей итерации с ботом
- Утечек credentials не добавлено; `generate.py` fail-fast-ится на отсутствующем `ANTHROPIC_API_KEY`
- Residual risk: live Claude generation на реальном API в этом окружении не подтверждена, потому что manual check остановился на missing `ANTHROPIC_API_KEY`; то есть код и моки зелёные, но production credential path ещё не проверен
