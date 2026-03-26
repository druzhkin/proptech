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

### Ретроспектива итерации 1

- Не сломал базовый import-path для `collect.py`: smoke import зелёный, а запуск `python src/collect.py` остаётся совместимым за счёт lazy import источников
- Основные edge cases этой итерации закрыты: missing env теперь не маскируется, временные сетевые ошибки получают retry, отсутствие транскрипта деградирует в description
- Требования `R1/P0` закрыты частично, но по существу: fail-fast env, retry/backoff, совместимость с transcript API и тестовый контур готовы; fallback на `evergreen_topics.json` остаётся в `P1`
- Утечек credentials не добавлено: TLS bypass убран, ключи продолжают читаться только из `config/.env`
- Residual risk: парсер Perplexity всё ещё иногда сваливается в единый digest при нестандартной разметке ответа; это уже не P0 по надёжности запуска, но ещё не закрывает качество контента до конца
