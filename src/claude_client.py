#!/usr/bin/env python3
"""
Client for Anthropic Claude API.

Provides two functions:
- filter_articles: selects top N articles for the Telegram channel
- generate_post: generates a Telegram post from a single article
"""

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

FILTER_SYSTEM = """Ты помогаешь отобрать новости для Telegram-канала PropTech Russia.
Аудитория — CTO застройщиков, коммерческие директора, руководители продукта.

Критерии отбора (по приоритету):
1. Конкретный измеримый результат (цифры, метрики) > абстрактные анонсы
2. Применимость для жилого девелопмента
3. Баланс категорий — не больше 2 статей из одной категории
4. Минимум 1 из Китая/Азии (если есть в исходных данных)
5. Минимум 1 про продукт/маркетинг/продажи (не только стройка)
6. Не больше 1 статьи про одну компанию

Если статей меньше 5 — выбери все подходящие, не добавляй неподходящие ради количества.

Верни строго JSON (без markdown-обёртки, без ```json```) в формате:
[
  {"id": "uuid статьи", "reason": "почему выбрана, 1 предложение"}
]"""

GENERATE_SYSTEM = """Ты пишешь пост для Telegram-канала PropTech Russia.

Автор канала — Даниил, 15 лет аналитическим директором в девелопменте. Создал 8 AI-инструментов для автоматизации процессов в строительстве.

═══ ГОЛОС И СТИЛЬ ═══

- Прямо, без воды и корпоративного жаргона
- С цифрами — каждое утверждение подкреплено данными
- С позицией — конкретный вывод, не "с одной стороны, с другой"
- С иронией когда уместно: "маркетинг говорит бизнес-класс, реальность — комфорт+"
- Пиши как умный коллега объясняет другому профессионалу, не как журналист

═══ СТРУКТУРА ПОСТА ═══

📌 [Хук — ОДНО предложение. Результат или провокация. НЕ "компания X анонсировала Y".
Хорошо: "3000 планировок за 3 секунды на обычном ноутбуке"
Хорошо: "$270M на роботов, которые кладут кирпич быстрее бригады из 10 человек"
Плохо: "Компания TestFit представила новый инструмент генеративного дизайна"]

[Что делает компания/продукт — 2-3 предложения. Без маркетинга, как коллеге-инженеру]

Результат: [конкретные цифры]. Кто использует: [названия компаний].

Как это работает: [2-3 предложения, техническим но понятным языком. Не "использует передовые алгоритмы ML", а "камера на каске сравнивает фото стройки с BIM-моделью и отмечает отставания"]

[Ограничения — если есть, честно: "Но: работает только с Revit", "Но: протестировано на 3 объектах, масштаб неясен"]

[ОПЦИОНАЛЬНО — Применимость. ТОЛЬКО если есть конкретика:
- "Лицензия $500/мес, ROI при >5 корпусах в работе"
- "Работает с Revit. С Renga — не тестировали, но API открытый"
- "Нужен BIM Level 2 минимум"
Если конкретного нечего сказать — НЕ ПИШИ этот блок. НИКОГДА не пиши "а в России ничего подобного нет" или "на российском рынке пока..."]

Источник: [ссылка]
[Если YouTube: 🎥 Видео: ссылка]

#PropTech #AI #[1-2 тега по теме: ConTech, BIM, GenDesign, SmartBuilding, MarTech, Robotics, Pricing, VirtualStaging, DigitalTwin, Modular, CRM]

═══ ЖЁСТКИЕ ПРАВИЛА ═══

- Русский язык
- 200-500 слов (считай!)
- Эмодзи: ТОЛЬКО 📌📊💡🤖🎥 — ничего другого
- ЗАПРЕЩЕНО: "уникальный", "эксклюзивный", "не имеет аналогов",
  "революционный", "инновационный", "передовой"
- ЗАПРЕЩЕНО: "а в России...", "на российском рынке...", "у нас пока..."
- ЗАПРЕЩЕНО: кликбейт, гарантии, преувеличения
- Если данных нет — писать прямо: "метрик в открытом доступе нет"
- НЕ выдумывать цифры и факты"""


def filter_articles(articles: list[dict], max_select: int = 5) -> list[dict]:
    """Select top articles using Claude. Returns list of {id, reason} dicts."""
    client = anthropic.Anthropic()

    summaries = []
    for a in articles:
        summaries.append({
            "id": a["id"],
            "title": a["title"],
            "source_name": a["source_name"],
            "source_type": a["source_type"],
            "category_hint": a.get("category_hint", "unknown"),
            "text_preview": a["text"][:1000],
        })

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=FILTER_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Выбери до {max_select} лучших статей из списка:\n\n"
                f"{json.dumps(summaries, ensure_ascii=False, indent=2)}"
            ),
        }],
    )

    logger.info(
        "filter_articles tokens: input=%d, output=%d",
        message.usage.input_tokens,
        message.usage.output_tokens,
    )

    response_text = message.content[0].text
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]

    return json.loads(cleaned)


def generate_post(article: dict) -> str:
    """Generate a Telegram post from a single article. Returns post text."""
    client = anthropic.Anthropic()

    source_label = "🎥 Видео" if article["source_type"] == "youtube" else "Источник"

    article_context = (
        f"Источник: {article['source_name']} ({article['source_type']})\n"
        f"Заголовок: {article['title']}\n"
        f"URL: {article['url']}\n"
        f"Категория: {article.get('category_hint', 'unknown')}\n"
        f"Тип ссылки для поста: {source_label}\n\n"
        f"Полный текст:\n{article['text'][:4000]}"
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=GENERATE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Напиши пост для Telegram на основе этой статьи:\n\n{article_context}",
        }],
    )

    logger.info(
        "generate_post tokens: input=%d, output=%d",
        message.usage.input_tokens,
        message.usage.output_tokens,
    )

    return message.content[0].text
