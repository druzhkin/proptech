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

## Итерация 4 — 2026-03-26

### Цель итерации

Собрать текущие рабочие куски в честный orchestration layer и выровнять документацию под фактическое состояние репозитория.

### Задачи

- [x] TASK-1: Реализовать `pipeline.py` как единый entry point `collect -> generate` c корректной остановкой на non-zero collect exit code и понятными exit codes `0/1/2` — агент: Coder
- [x] TASK-2: Обновить `README.md` и `CLAUDE.md`, чтобы они отражали текущие команды, архитектуру и ограничения проекта, а не только старый сборщик — агент: Coder
- [x] TASK-3: Обновить `config/.env.example` понятными комментариями к переменным и отмеченным фактом, что `ANTHROPIC_API_KEY` нужен для `generate.py` — агент: Coder
- [x] TASK-4: Добавить минимальные тесты на orchestration и прогоны документационно-эксплуатационных smoke-paths — агент: Tester
- [x] TASK-5: Прогнать quality gates и обновить журнал итерации с остаточными рисками — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для нового набора тестов
- [x] smoke-тест: `python -c "from src.generate import main; print('generate OK')"`
- [x] manual-check: `python pipeline.py` даёт предсказуемый orchestration result или понятный fail-fast

### Замечания по объёму

- `bot.py` и Telegram review flow всё ещё вне объёма этой итерации
- live generate step может остаться непроверенным до появления рабочего `ANTHROPIC_API_KEY`, но pipeline orchestration должен быть корректным и без этого

### Лог работ

- [CODE] `pipeline.py`: добавлен честный orchestration entry point `collect -> generate` с остановкой на non-zero collect exit code и возвратом итогового кода шага генерации
- [CODE] `README.md`, `CLAUDE.md`, `config/.env.example`: документация и env-шаблон выровнены под фактическое состояние репозитория, включая `generate.py`, `pipeline.py` и текущие ограничения по bot/review flow
- [TEST] `tests/test_pipeline.py`: добавлены проверки на остановку pipeline при ошибке collect и на корректный запуск generate после успешного collect
- [CRITIC] Прогнаны quality gates: `ruff check src/ tests/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.generate import main; print('generate OK')"`
- [CRITIC] Manual-check проведён в двух режимах: живой `python pipeline.py` уткнулся в runtime-риск `youtube-transcript-api`/YouTube IP blocking, а принудительный fail-fast path через пустые `PERPLEXITY_API_KEY/YOUTUBE_API_KEY/ANTHROPIC_API_KEY` подтвердил корректную остановку pipeline без запуска generate

### Ретроспектива итерации 4

- `R4` больше не теоретический: в репозитории есть реальный `pipeline.py`, который не пытается запускать `generate`, если `collect` уже вернул non-zero
- Документация перестала врать о состоянии проекта: `README.md`, `CLAUDE.md` и `.env.example` теперь соответствуют тому, что действительно можно запустить
- Утечек credentials не добавлено; pipeline и дочерние CLI по-прежнему берут конфигурацию только из env/`config/.env`
- Live manual run выявил не абстрактную, а реальную эксплуатационную проблему: YouTube transcript path может подвисать на сетевых ретраях и IP blocking, поэтому production-надёжность `R1` всё ещё ограничена внешней средой
- Residual risk: `pipeline.py` orchestrates шаги корректно, но end-to-end live success в этом окружении остаётся зависимым от внешних API и наличия рабочего `ANTHROPIC_API_KEY`

## Итерация 5 — 2026-03-26

### Цель итерации

Закрыть первый рабочий thin slice `R3`: дать админу минимальный, но реальный Telegram review/publish flow поверх уже существующих `drafts`.

### Задачи

- [x] TASK-1: Реализовать `src/bot.py` как admin-only long-polling bot с командами `/drafts` и `/status`, inline-действиями Publish/Edit/Skip и понятными ошибками вместо тихих падений — агент: Coder
- [x] TASK-2: Добавить файловую логику review-state: загрузка последних draft-файлов, безопасный поиск draft по short id/full id, запись `published`-результатов и сохранение admin-изменений текста — агент: Coder
- [x] TASK-3: Зафиксировать terminal state для bot-flow в `data/drafts`: не терять `published` и `skipped` записи при rerun генерации — агент: Coder
- [x] TASK-4: Добавить `pytest`-покрытие для bot helper-логики: status counters, short id resolution, save/publish paths и fallback публикации без фото — агент: Tester
- [x] TASK-5: Прогнать quality gates, smoke import `src.bot` и обновить журнал итерации с остаточными рисками Telegram publish path — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для нового набора тестов
- [x] smoke-тест: `python -c "from src.bot import main; print('bot OK')"`
- [x] manual-check: `src.bot` корректно загружается, fail-fast-ится на отсутствующих Telegram env и умеет сериализовать review-state без сетевого вызова к Telegram

### Замечания по объёму

- Для этой итерации не добавляется новая зависимость: бот строится поверх уже имеющегося `requests`, а не через отдельный Telegram SDK
- Полный live publish в реальный канал может остаться непроверенным без рабочего `TG_BOT_TOKEN`/`TG_CHANNEL_ID`, но локальная логика статусов и fallback-пути должна быть закрыта тестами

### Лог работ

- [CODE] `src/bot.py`: добавлен admin-only long-polling bot на `requests` с `/start`, `/drafts`, `/status`, `/cancel`, inline Publish/Edit/Skip, fail-fast проверкой Telegram env и fallback-публикацией текстом при ошибке отправки фото
- [CODE] `src/bot.py`: реализованы helper-слои для загрузки последнего draft batch, безопасного short-id/full-id lookup, форматирования preview, сохранения admin edit и записи `data/published/YYYY-MM-DD.json`
- [CODE] `src/generate.py`: merge-логика rerun обновлена так, чтобы не затирать `published`, `skipped` и `edited_by_admin` записи после работы бота
- [CODE] `README.md`, `CLAUDE.md`, `config/.env.example`: документация и env-шаблон обновлены под реальное наличие `bot.py` и `data/published`
- [TEST] `tests/test_bot.py`, `tests/test_generate.py`: добавлены тесты на status counters, collision-safe short ids, запись published state, фото-fallback и сохранность `skipped`/admin-edited записей при rerun генерации
- [CRITIC] Прогнаны quality gates: `ruff check src/ tests/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.bot import main; print('bot OK')"`, `python -c "from src.generate import main as generate_main; print('generate OK')"`, `python -c "from src.collect import main as collect_main; print('collect OK')"`
- [CRITIC] Manual-check: `src.bot.main(['--once'])` корректно fail-fast-ится на пустых `TG_BOT_TOKEN/TG_CHANNEL_ID/TG_ADMIN_ID`, а `record_publication(...)` сериализует `published` state локально без сетевого вызова

### Ретроспектива итерации 5

- `R3` больше не пустое место: в репозитории есть реальный `src/bot.py`, который может провести admin через `/drafts` и `/status`, сохранить правки и записать публикацию в `data/published`
- Решение сознательно не добавляет Telegram SDK: raw Bot API через `requests` проще для этого репозитория и не тащит лишнюю зависимость ради базового long polling
- Самая опасная интеграционная дыра закрыта не “красивым UI”, а сохранностью состояния: rerun `generate.py` теперь не должен стирать `published`, `skipped` и admin-edited draft records
- Утечек credentials не добавлено; бот стартует только при наличии явных Telegram env, а без них завершает работу понятной ошибкой
- Residual risk: live publish path в реальный Telegram-канал и реальное long-poll взаимодействие не подтверждены в этом окружении, потому что нет проверенных рабочих `TG_BOT_TOKEN`/`TG_CHANNEL_ID`; локальная логика и файловая интеграция зелёные, но production credential path ещё не проверен

## Итерация 6 — 2026-03-26

### Цель итерации

Перевести `R2` с Anthropic SDK на OpenRouter API без ломки уже существующего generate flow.

### Задачи

- [x] TASK-1: Заменить SDK-клиент Anthropic в `src/claude_client.py` на OpenRouter chat completions API через `requests`, сохранив retry/backoff и JSON parsing — агент: Coder
- [x] TASK-2: Перевести `src/generate.py`, `config/.env.example`, `README.md`, `CLAUDE.md` и `requirements.txt` на `OPENROUTER_API_KEY` и убрать `anthropic` dependency — агент: Coder
- [x] TASK-3: Добавить/обновить тесты на OpenRouter-compatible response shape и новый env path генерации — агент: Tester
- [x] TASK-4: Прогнать quality gates и smoke/fail-fast проверки для OpenRouter path — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ tests/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для обновлённого набора тестов
- [x] smoke-тест: `python -c "from src.generate import main; print('generate OK')"`
- [x] manual-check: `generate.py` корректно fail-fast-ится на отсутствующем `OPENROUTER_API_KEY`

### Замечания по объёму

- Файл `src/claude_client.py` оставлен по имени как слой совместимости, но внутри теперь ходит в OpenRouter, а не в Anthropic SDK
- По умолчанию клиент использует `OPENROUTER_MODEL=anthropic/claude-sonnet-4`, но модель теперь можно переопределить через env без правки кода

### Лог работ

- [CODE] `src/claude_client.py`: Anthropic SDK выпилен, добавлен OpenRouter HTTP client на `requests` с OpenAI-compatible `choices[0].message.content`, retry/backoff на network/429/5xx и optional headers `OPENROUTER_SITE_URL`/`OPENROUTER_APP_NAME`
- [CODE] `src/generate.py`: fail-fast path переведён на `OPENROUTER_API_KEY`, при этом existing generate flow и merge-логика не изменены по поведению
- [CODE] `README.md`, `CLAUDE.md`, `config/.env.example`, `requirements.txt`: документация и env/dep layer выровнены под OpenRouter вместо Anthropic SDK
- [TEST] `tests/test_claude_client.py`, `tests/test_generate.py`: добавлены/обновлены тесты на OpenRouter response shape и новый env path `OPENROUTER_API_KEY`
- [CRITIC] Прогнаны quality gates: `ruff check src/ tests/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.generate import main; print('generate OK')"`
- [CRITIC] Manual-check: `generate.py` корректно останавливается на missing `OPENROUTER_API_KEY`; live OpenRouter request подтверждён 2026-03-26 через реальный ключ, `python src/generate.py --max 1` успешно создал draft в `data/drafts/2026-03-26.json`

### Ретроспектива итерации 6

- Замена провайдера закрыта без ломки `R2`: generate path остался рабочим, но больше не зависит от `anthropic` Python package
- OpenRouter здесь не “новая фича”, а замена transport/provider layer: промпты, валидация и fallback-selection остались прежними
- Утечек credentials не добавлено; provider key теперь берётся только из `OPENROUTER_API_KEY`
- Residual risk: OpenRouter transport и production key path в этом окружении уже подтверждены, но качество генерации всё ещё зависит от конкретной модели, лимитов аккаунта и внешней доступности провайдера; кроме того, сам ключ после публикации в чате нужно считать скомпрометированным и перевыпустить

## Итерация 7 — 2026-03-27

### Цель итерации

Перевести проект из “технически работает” в более честный редакторский и operational MVP: ужесточить редакционную политику по технологиям, убрать зависимость бота от ручного `TG_ADMIN_ID` и подготовить живой deployment-контур.

### Задачи

- [x] TASK-1: Ужесточить editorial policy в `src/generate.py`, `src/claude_client.py` и `config/prompt.md`, чтобы в drafts попадали технологические кейсы, а не раунды, сделки и рыночный шум — агент: Coder
- [x] TASK-2: Сделать `src/bot.py` работоспособным без обязательного `TG_ADMIN_ID` через безопасную проверку администратора канала в Telegram API — агент: Coder
- [x] TASK-3: Добавить/обновить `pytest`-покрытие для editorial filtering, human-style validation и нового Telegram auth path — агент: Tester
- [ ] TASK-4: Проверить live-контур с реальными Telegram credentials и попытаться привязать/deploy-нуть Railway service без коммита секретов — агент: Critic
- [x] TASK-5: Обновить `README.md`, `config/.env.example` и журнал итерации по итогам фактического результата — агент: Critic

### Критерии готовности итерации

- [x] `ruff check src/ tests/ --fix` проходит без ошибок
- [x] `mypy src/ --ignore-missing-imports` проходит без новых ошибок
- [x] `pytest tests/ -v --tb=short` проходит для обновлённого набора тестов
- [x] smoke-тест: `python -c "from src.generate import main; print('generate OK')"`
- [x] smoke-тест: `python -c "from src.bot import main; print('bot OK')"`

### Замечания по объёму

- Railway deployment не закрыт не из-за кода, а из-за невалидного `RAILWAY_TOKEN`: CLI возвращает `Invalid RAILWAY_TOKEN`, поэтому живой деплой в этом цикле честно не подтверждён
- В `data/articles/2026-03-27.json` уже лежали мусорные Perplexity-ответы из прошлого прогона; данные не удалялись, но generation теперь умеет отбрасывать такие записи как `invalid_source_content`

### Лог работ

- [CODE] `src/claude_client.py`: generation prompt переписан под более человеческий русский тон без first-person voice, с вариативными style profiles и жёстким запретом на funding-round / PR-driven фокус
- [CODE] `src/generate.py`: добавлен editorial prefilter для finance-first и invalid-source статей; такие записи получают `rejected` вместо попадания в drafts
- [CODE] `src/perplexity_client.py`, `config/prompt.md`: upstream prompt и Perplexity system prompt усилены под live web search; limitation/meta-ответы теперь распознаются и не считаются новостями
- [CODE] `src/bot.py`: `TG_ADMIN_ID` стал optional; если он не задан, бот авторизует реальных администраторов канала через Telegram `getChatMember`
- [CODE] `README.md`, `CLAUDE.md`, `config/.env.example`, `Procfile`: документация и deployment hints выровнены под editorial policy, dynamic Telegram auth и Railway worker start
- [TEST] `tests/test_bot.py`, `tests/test_claude_client.py`, `tests/test_generate.py`, `tests/test_perplexity_client.py`: добавлены тесты на first-person validation, editorial reject path, invalid-source filtering и новый Telegram auth path
- [CRITIC] Прогнаны quality gates: `ruff check src/ tests/ --fix`, `mypy src/ --ignore-missing-imports`, `pytest tests/ -v --tb=short`, `python -c "from src.generate import main; print('generate OK')"`, `python -c "from src.bot import main; print('bot OK')"`
- [CRITIC] Live-check: `python src/collect.py --engine perplexity` создал свежий batch `data/articles/2026-03-27.json`; `python src/generate.py --date 2026-03-27 --max 5` дал `drafts=5 rejected=4`; `python src/bot.py --once` успешно стартует с `TG_BOT_TOKEN` и `TG_CHANNEL_ID` даже без `TG_ADMIN_ID`
- [CRITIC] Railway-check: `railway status` и `railway variable list` с предоставленным токеном завершаются `Invalid RAILWAY_TOKEN`, поэтому live deploy не выполнен

### Ретроспектива итерации 7

- Проект перестал быть “генератором всего подряд”: finance-first и мусорные meta-ответы теперь отсекаются до генерации, а в live batch реально попали технологические кейсы по 3D-печати, модульному строительству и геодезическим дронам
- Telegram operational gap заметно сократился: bot больше не требует ручного поиска `TG_ADMIN_ID`, если пользователь действительно админ целевого канала
- Самый неприятный runtime-баг этой итерации был не в OpenRouter, а в upstream collection: Perplexity один раз вернул limitation text вместо новостей; теперь такой ответ не маскируется под “успешный сбор”
- Residual risk: Railway deployment остаётся неподтверждённым, пока не будет рабочего токена или project access; кроме того, уже опубликованные в чате Telegram/OpenRouter secrets нужно считать скомпрометированными и перевыпустить
