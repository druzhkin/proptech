# PropTech Pipeline — AGENTS.md
# Инструкция для Codex: полностью автономная разработка

---

## 0. ПРОЧИТАЙ ПЕРЕД НАЧАЛОМ

Ты работаешь над Python-пайплайном для Telegram-канала о PropTech.
Проект собирает новости через Perplexity API и YouTube, генерирует посты через Claude, 
публикует через Telegram-бота с ревью-интерфейсом.

**Репозиторий:** https://github.com/druzhkin/proptech  
**Спека:** `specs/requirements.md` — ОБЯЗАТЕЛЬНО прочитай перед первой итерацией.

---

## 1. ОКРУЖЕНИЕ И КОМАНДЫ

```bash
# Установка зависимостей
pip install -r requirements.txt

# Проверка синтаксиса и стиля
ruff check src/ --fix
mypy src/ --ignore-missing-imports

# Тесты
pytest tests/ -v --tb=short

# Запуск сбора новостей
python src/collect.py

# Генерация постов
python src/generate.py --max 5

# Запуск бота (только для smoke-теста — не запускать надолго)
timeout 5 python src/bot.py || true

# Проверка импортов
python -c "from src.collect import main; print('OK')"
python -c "from src.generate import main; print('OK')"
python -c "from src.bot import main; print('OK')"
```

---

## 2. СТЕК И АРХИТЕКТУРА

```
config/
  .env.example       — шаблон переменных (PERPLEXITY_API_KEY, YOUTUBE_API_KEY, 
                        ANTHROPIC_API_KEY, TG_BOT_TOKEN, TG_CHANNEL_ID, TG_ADMIN_ID)
  channels.json      — YouTube-каналы с channel_id
  evergreen_topics.json — резервный банк тем
  prompt.md          — промпт для Perplexity (русский, структурированный)

src/
  collect.py         — главный скрипт сбора (Perplexity + YouTube)
  perplexity_client.py — клиент Perplexity API (sonar-deep-research)
  youtube_client.py  — YouTube Data API v3 + транскрипты
  find_channels.py   — поиск channel_id по названию
  claude_client.py   — Claude API: filter_articles(), generate_post(), validate_post()
  generate.py        — генерация черновиков постов через Claude
  bot.py             — Telegram-бот (long-polling, только admin)

data/
  articles/YYYY-MM-DD.json  — сырые статьи
  drafts/YYYY-MM-DD.json    — сгенерированные черновики
  published/YYYY-MM-DD.json — опубликованные посты

specs/
  requirements.md    — спека итогового результата (твоя задача)
  tasks.md           — план итерации (пишешь сам перед каждой итерацией)
  audit.md           — результаты аудита (пишешь после первого анализа)
```

**Data schema (Article):**
```json
{
  "id": "uuid",
  "source_type": "perplexity|youtube",
  "source_name": "string",
  "title": "string",
  "url": "string",
  "text": "string (full text or transcript)",
  "image_url": "string | null",
  "date": "YYYY-MM-DD",
  "category_hint": "string",
  "collected_at": "ISO datetime"
}
```

---

## 3. АВТОНОМНЫЙ РАБОЧИЙ ПРОЦЕСС

### Шаг 1 — Аудит (первый запуск, только один раз)

```
1. Прочитай specs/requirements.md полностью
2. Прочитай ВЕСЬ исходный код: src/*.py, config/*.json, config/prompt.md
3. Сформулируй список проблем, рисков и зон улучшения
4. Запиши результат в specs/audit.md:
   - Критические баги (блокирующие работу)
   - Архитектурные проблемы
   - Отсутствующие фичи из спеки
   - Качество кода (типизация, тесты, логирование)
   - Оценка приоритетов (P0/P1/P2)
5. Создай specs/tasks.md с планом первой итерации (не более 5 задач)
```

### Шаг 2 — Планирование итерации

Перед каждой итерацией запиши в `specs/tasks.md`:
```markdown
## Итерация N — [дата]

### Цель итерации
[одно предложение — чего хотим достичь]

### Задачи
- [ ] TASK-1: [описание] — агент: [Coder/Tester/Critic]
- [ ] TASK-2: ...

### Критерии готовности итерации
- [ ] ruff check проходит без ошибок
- [ ] mypy проходит без новых ошибок
- [ ] pytest проходит (или тесты написаны для новой функциональности)
- [ ] smoke-тест: python -c "from src.X import main; print('OK')"
```

### Шаг 3 — Реализация (Coder Agent)

- Пиши код по одной задаче за раз
- После каждого файла: `ruff check {file} --fix`
- Используй type hints на всех функциях
- Логируй через `logging`, не через `print()`
- Никогда не хардкодь API-ключи
- Все пути — через `PROJECT_ROOT / "..."` (pathlib)

### Шаг 4 — Проверка (Tester Agent)

После реализации каждой задачи:
```bash
ruff check src/ --fix
mypy src/ --ignore-missing-imports
pytest tests/ -v --tb=short 2>&1 | tail -30
python -c "from src.collect import main; print('collect OK')"
python -c "from src.generate import main; print('generate OK')"
```

Если тесты упали — фикси сам, до 3 попыток. После 3 неудач — спроси меня.

### Шаг 5 — Критика (Critic Agent)

После завершения задачи задай себе вопросы:
1. Не сломал ли я что-то, что работало?
2. Есть ли edge cases, которые я не обработал?
3. Соответствует ли это requirements.md?
4. Нет ли утечки данных / credentials?
5. Работает ли error handling (never crash philosophy)?

Запиши выводы в конец `specs/tasks.md` как `### Ретроспектива итерации N`.

### Шаг 6 — Коммит

```bash
git add -A
git commit -m "feat/fix/chore: [описание изменений]

- что сделано
- что исправлено
- что проверено"
git push origin feature/iteration-N
```

Затем открой PR с описанием итерации.

---

## 4. АВТОНОМНОЕ ПРИНЯТИЕ РЕШЕНИЙ

### Делай сам (не спрашивай):
- ✅ Рефакторинг кода без изменения поведения
- ✅ Добавление type hints и docstrings
- ✅ Исправление ruff/mypy ошибок
- ✅ Написание тестов для существующей логики
- ✅ Добавление обработки ошибок (try/except + logging)
- ✅ Оптимизация запросов к API (retry, backoff)
- ✅ Добавление новых полей в data schema (обратно совместимо)
- ✅ Улучшение промптов в config/prompt.md
- ✅ Добавление новых аргументов CLI

### Спроси меня сначала (⚠️):
- ⚠️ Изменение структуры JSON-схемы (breaking change)
- ⚠️ Смена модели (claude-sonnet → claude-opus и т.п.)
- ⚠️ Добавление новых API-интеграций (новые ключи нужны)
- ⚠️ Изменение логики публикации в Telegram
- ⚠️ Удаление или переименование существующих функций
- ⚠️ Изменение config/channels.json (там реальные данные)
- ⚠️ Если задача займёт >200 строк нового кода — согласуй подход

### Никогда (🚫):
- 🚫 Не хардкодь API-ключи в коде
- 🚫 Не коммить config/.env (он в .gitignore)
- 🚫 Не удаляй данные из data/ папки
- 🚫 Не пушь напрямую в main
- 🚫 Не меняй .gitignore
- 🚫 Не устанавливай зависимости с известными CVE

---

## 5. МУЛЬТИАГЕНТНАЯ АРХИТЕКТУРА

Когда задача сложная (>3 файлов изменений), используй роли явно:

```
[AUDIT]   — первичное исследование кода и проблем
[PLAN]    — составление tasks.md для итерации
[CODE]    — написание/изменение исходного кода
[TEST]    — написание тестов, запуск проверок
[CRITIC]  — поиск багов, edge cases, архитектурных проблем
[COMMIT]  — git add/commit/push, открытие PR
[ASK]     — формулировка вопроса для пользователя (только когда stuck)
```

Для каждого изменения в лог записывай какой агент что сделал.

---

## 6. КАЧЕСТВО КОДА

- **Type hints**: обязательны на всех публичных функциях
- **Docstrings**: на всех модулях и публичных функциях
- **Logging**: `logger = logging.getLogger(__name__)`, не print()
- **Error handling**: try/except с логированием, никогда не raise без catch выше
- **Paths**: только через `pathlib.Path` и `PROJECT_ROOT`
- **Tests**: pytest, файлы в `tests/`, покрытие > 60% для новой логики
- **Commits**: conventional commits (`feat:`, `fix:`, `chore:`, `test:`, `refactor:`)

---

## 7. КОГДА ЗАДАВАТЬ ВОПРОСЫ

Задавай вопрос мне только если:
1. После 3 попыток что-то не работает
2. Требуется внешний ресурс/ключ/доступ которого нет
3. Два варианта решения принципиально разные (разная архитектура)
4. Нашёл критический баг в production-логике (публикация в канал)

Формат вопроса:
```
[ASK] Ситуация: {что происходит}
Пробовал: {что пробовал}
Варианты: A) {вариант А} | B) {вариант В}
Рекомендую: A, потому что {причина}
```
