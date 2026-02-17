#!/usr/bin/env python3
"""
Client for Anthropic Claude API.

Two functions:
- filter_articles: selects top N articles via Claude with strict rejection criteria
- generate_post: generates a Telegram post with validation loop and retry
"""

import json
import logging
import re

import anthropic

logger = logging.getLogger(__name__)

FILTER_SYSTEM = """Ты фильтруешь новости для экспертного Telegram-канала PropTech Russia.
Аудитория — CTO застройщиков, коммерческие директора, руководители продукта.
Это жёсткие профессионалы. Им нельзя подсовывать пустышки.

═══ КРИТЕРИИ ОТБОРА ═══

Статья ПРОХОДИТ если:
- Есть конкретное внедрение у реальной компании (не "пилотный проект планируется")
- Есть измеримый результат: цифры производительности, экономии, скорости
- Технология применима к жилому девелопменту (не только коммерческая недвижимость)
- Это не пересказ пресс-релиза, а реальный кейс или значимый продукт

═══ ОБЯЗАТЕЛЬНО ОТКЛОНИ статью если ═══

- Нет НИ ОДНОГО реального внедрения — только планы, патенты, прототипы, концепты
- Единственная значимая цифра — сумма инвестиций/раунда
- Единственный "клиент" — пилот без результатов
- Это AI-washing: обычный продукт с приклеенным словом "AI"
- Проект "существует на бумаге" или "планируется к запуску"
- Новость про коммерческую недвижимость/офисы без связи с жилым строительством

═══ БАЛАНС ═══

- Не больше 2 статей из одной категории
- Минимум 1 из Китая/Азии (если есть достойная)
- Минимум 1 про маркетинг/продажи/ценообразование (если есть достойная)
- Не больше 1 статьи про одну компанию

═══ ФОРМАТ ОТВЕТА ═══

Верни ТОЛЬКО JSON массив, без markdown-обёртки, без ```json```, без пояснений до/после.
Если достойных статей меньше 5 — верни сколько есть. НЕ добавляй слабые ради количества.
Лучше 3 сильных поста чем 5 с мусором.

[
  {"id": "uuid", "reason": "одно предложение почему прошла фильтр"},
  ...
]

Если ни одна статья не проходит критерии — верни пустой массив []."""


GENERATE_SYSTEM = """Ты пишешь пост для Telegram-канала PropTech Russia.

Автор канала — Даниил, 15 лет аналитическим директором в девелопменте (Группа Родина, Москва). Создал 8 AI-инструментов для автоматизации процессов в строительстве. Пишет как практик, не как журналист.

═══ СТРУКТУРА ПОСТА (строго в этом порядке) ═══

СТРОКА 1: 📌 [ХУК]
- Одно предложение. Максимум 15 слов
- Это РЕЗУЛЬТАТ или ПРОВОКАЦИЯ, не описание
- Хорошие хуки: цифра + что она значит
  ✅ "$270M на робота-экскаваторщика — ставится за 4 часа"
  ✅ "3000 планировок за 3 секунды на обычном ноутбуке"
  ✅ "AI-оценщик недвижимости ошибается на 6% — дешевле живого"
- Плохие хуки: описание компании или процесса
  ❌ "Компания Bedrock Robotics привлекла инвестиции на развитие"
  ❌ "Новая платформа использует AI для автоматизации строительства"
  ❌ "Китайский предприниматель создал инновационную систему"

ПУСТАЯ СТРОКА

БЛОК 2: ЧТО ДЕЛАЕТ (2-3 предложения)
- Компания, страна — что конкретно делает продукт
- Как объяснил бы коллеге за кофе, не как пресс-релиз
- Без слов "инновационный", "революционный", "передовой"

ПУСТАЯ СТРОКА

БЛОК 3: РЕЗУЛЬТАТ И КЛИЕНТЫ (1-2 предложения)
- "Результат: [цифры]. Кто использует: [компании]."
- Если цифр нет — написать "Метрик в открытом доступе нет"
- Если клиентов нет — написать "Публичных внедрений пока нет"
- Не выдумывать. Не округлять. Не преувеличивать

ПУСТАЯ СТРОКА

БЛОК 4: КАК РАБОТАЕТ (2-3 предложения)
- Технически но понятно. Не "использует ML-алгоритмы",
  а "камера на каске снимает стройку, сравнивает с BIM и красит
  отстающие участки красным"
- Если из источника непонятно как работает — не выдумывай,
  напиши "детали архитектуры не раскрыты"

ПУСТАЯ СТРОКА

БЛОК 5: ОГРАНИЧЕНИЯ (1-2 предложения, если есть)
- Начинай с "Но:"
- Честные ограничения: стадия, масштаб, совместимость, цена
- Если источник не упоминает ограничений — можешь не писать этот блок

ПУСТАЯ СТРОКА

БЛОК 6 (ОПЦИОНАЛЬНО): ПРИМЕНИМОСТЬ
- ТОЛЬКО если есть конкретика: цена лицензии, совместимость с софтом,
  минимальный масштаб проекта, ROI
- ✅ "Лицензия от $500/мес. Окупается при >5 корпусах"
- ✅ "Работает с Revit и IFC. Интеграция с Renga — под вопросом"
- ❌ НЕ ПИШИ: "а в России...", "на российском рынке...", "у нас пока..."
- ❌ НЕ ПИШИ: общие слова про "перспективы внедрения"
- Если конкретики нет — НЕ ПИШИ этот блок вообще. Пустой блок хуже чем никакого

ПУСТАЯ СТРОКА

ПОСЛЕДНЯЯ СТРОКА: Источник: [URL]
Если YouTube: добавь строку 🎥 Видео: [URL]

ПОСЛЕДНЯЯ СТРОКА: теги
#PropTech #AI #[1-2 тега: ConTech, BIM, GenDesign, SmartBuilding, MarTech, Robotics, Pricing, VirtualStaging, DigitalTwin, Modular, CRM]

═══ ЖЁСТКИЕ ПРАВИЛА ═══

1. ОДИН пост = ОДНА компания/продукт. Не упоминай другие компании
   "заодно" или "параллельно". Либо они заслуживают отдельного поста,
   либо не упоминай

2. Длина: 250-450 слов. Это жёсткие рамки. Считай

3. Русский язык. Термины можно на английском (BIM, IoT, LiDAR)

4. Эмодзи: ТОЛЬКО 📌💡🤖🎥 — больше никаких

5. ЗАПРЕЩЁННЫЕ СЛОВА (не используй ни в какой форме):
   уникальный, эксклюзивный, не имеет аналогов,
   революционный, инновационный, передовой, прорывной,
   беспрецедентный, не имеющий аналогов, впервые в мире

6. Если цифра из источника кажется неправдоподобной или раздутой —
   напиши "по данным компании" и не подавай как факт.
   Ты пишешь для экспертов — они заметят враньё

7. НЕ начинай пост с названия компании. Начинай с результата

8. НЕ выдумывай данные. Если в источнике нет цифры — не добавляй"""


def filter_articles(articles: list[dict], max_select: int = 5) -> list[dict]:
    """
    Claude выбирает лучшие статьи из списка.
    Возвращает список {"id": ..., "reason": ...}.
    При ошибке парсинга — retry 1 раз. При повторной ошибке — возвращает все статьи.
    """
    client = anthropic.Anthropic()

    # Краткие описания для Claude (не гнать полный текст 10 статей)
    summaries = []
    for a in articles:
        summaries.append({
            "id": a["id"],
            "title": a["title"],
            "source_name": a["source_name"],
            "source_type": a["source_type"],
            "category_hint": a.get("category_hint", "unknown"),
            "text_preview": a["text"][:1500],  # достаточно для оценки
        })

    user_msg = (
        f"Отбери до {max_select} лучших статей. "
        f"Строго примени критерии — не пропускай мусор.\n\n"
        f"{json.dumps(summaries, ensure_ascii=False, indent=2)}"
    )

    for attempt in range(2):  # максимум 2 попытки
        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=FILTER_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            response_text = message.content[0].text.strip()

            # Убрать markdown-обёртку если Claude всё-таки добавил
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
                response_text = response_text.rsplit("```", 1)[0].strip()

            result = json.loads(response_text)

            # Валидация: результат должен быть списком словарей с полем "id"
            if not isinstance(result, list):
                raise ValueError("Ответ не массив")
            for item in result:
                if "id" not in item:
                    raise ValueError(f"Нет поля id: {item}")

            logger.info(
                "Фильтрация: выбрано %d из %d (попытка %d)",
                len(result), len(articles), attempt + 1,
            )
            # Логируем стоимость
            usage = message.usage
            logger.info(
                "Tokens: input=%d, output=%d",
                usage.input_tokens, usage.output_tokens,
            )

            return result

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Ошибка парсинга фильтра (попытка %d): %s", attempt + 1, e)
            if attempt == 0:
                continue
            else:
                # Fallback: вернуть все статьи без фильтрации
                logger.warning("Фильтрация не удалась, используем все статьи")
                return [
                    {"id": a["id"], "reason": "фильтрация не сработала"}
                    for a in articles[:max_select]
                ]

        except anthropic.APIError as e:
            logger.error("Anthropic API error: %s", e)
            return [
                {"id": a["id"], "reason": "API недоступен"}
                for a in articles[:max_select]
            ]

    return []


def generate_post(article: dict) -> str | None:
    """
    Генерирует один пост. При проблемах с валидацией — retry до 2 раз
    с указанием конкретных ошибок.
    """
    client = anthropic.Anthropic()

    article_context = (
        f"Источник: {article['source_name']} ({article['source_type']})\n"
        f"Заголовок: {article['title']}\n"
        f"URL: {article['url']}\n\n"
        f"Полный текст:\n{article['text'][:5000]}"
    )

    messages = [{"role": "user", "content": f"Напиши пост:\n\n{article_context}"}]

    for attempt in range(3):  # до 3 попыток
        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=GENERATE_SYSTEM,
                messages=messages,
            )

            post_text = message.content[0].text.strip()
            usage = message.usage
            logger.info(
                "Генерация (попытка %d): %d+%d tokens",
                attempt + 1, usage.input_tokens, usage.output_tokens,
            )

            # Валидация
            problems = validate_post(post_text)

            if not problems:
                return post_text

            if attempt < 2:
                # Retry с указанием конкретных проблем
                logger.info("Валидация не пройдена: %s. Retry...", problems)
                messages = [
                    {"role": "user", "content": f"Напиши пост:\n\n{article_context}"},
                    {"role": "assistant", "content": post_text},
                    {
                        "role": "user",
                        "content": (
                            "Исправь пост. Конкретные проблемы:\n"
                            + "\n".join(f"- {p}" for p in problems)
                            + "\n\nПерепиши пост целиком с исправлениями."
                        ),
                    },
                ]
            else:
                # Третья попытка не удалась — возвращаем как есть с пометкой
                logger.warning("Валидация не пройдена после 3 попыток: %s", problems)
                return post_text

        except anthropic.APIError as e:
            logger.error("Anthropic API error: %s", e)
            if attempt < 2:
                continue
            return None

    return None


def validate_post(text: str) -> list[str]:
    """
    Проверяет пост на соответствие правилам.
    Возвращает список проблем. Пустой список = всё ок.
    """
    problems = []
    words = text.split()
    word_count = len(words)

    # Длина
    if word_count < 200:
        problems.append(f"Слишком короткий: {word_count} слов, нужно минимум 250")
    if word_count > 550:
        problems.append(f"Слишком длинный: {word_count} слов, нужно максимум 450")

    # Хук
    if not text.startswith("\U0001f4cc"):  # 📌
        problems.append("Пост должен начинаться с 📌")
    else:
        # Проверить длину хука (первая строка)
        first_line = text.split("\n")[0]
        hook_words = len(first_line.split())
        if hook_words > 20:
            problems.append(f"Хук слишком длинный: {hook_words} слов, максимум 15")

    # Запрещённые слова
    forbidden = [
        "уникальн", "эксклюзивн", "не имеет аналогов",
        "революционн", "инновационн", "передовой", "прорывн",
        "беспрецедентн", "впервые в мире",
        "а в россии", "на российском рынке", "у нас пока",
    ]
    text_lower = text.lower()
    for word in forbidden:
        if word in text_lower:
            problems.append(f"Запрещённое слово/фраза: '{word}'")

    # Источник
    if "источник:" not in text_lower and "source:" not in text_lower:
        problems.append("Нет ссылки на источник (строка 'Источник: URL')")

    # Теги
    if "#PropTech" not in text and "#proptech" not in text.lower():
        problems.append("Нет тега #PropTech")

    # Запрещённые эмодзи
    allowed = {"\U0001f4cc", "\U0001f4a1", "\U0001f916", "\U0001f3a5"}  # 📌💡🤖🎥
    # Находим все эмодзи в тексте
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001F9FF"   # Misc Symbols and Pictographs + Emoticons + etc
        "\U00002600-\U000027BF"    # Misc symbols
        "\U0001FA00-\U0001FA6F"    # Chess Symbols
        "\U0001FA70-\U0001FAFF"    # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"    # Dingbats
        "]+",
        flags=re.UNICODE,
    )
    found_emoji = set(emoji_pattern.findall(text))
    # Разбиваем на отдельные символы
    all_emoji = set()
    for e in found_emoji:
        all_emoji.update(e)
    bad_emoji = all_emoji - allowed
    if bad_emoji:
        problems.append(
            f"Запрещённые эмодзи: {''.join(bad_emoji)}. Разрешены только: 📌💡🤖🎥"
        )

    # Несколько компаний (грубая проверка)
    multi_signals = ["параллельно", "отдельно:", "также стоит отметить", "кроме того,"]
    for signal in multi_signals:
        if signal in text_lower:
            problems.append(
                f"Похоже на пост-сборник (найдено '{signal}'). Один пост = одна компания"
            )

    return problems
