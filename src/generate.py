#!/usr/bin/env python3
"""
Генерация постов из собранных статей.

Использование:
  python src/generate.py                          # Последний файл articles
  python src/generate.py --date 2026-02-17        # Конкретная дата
  python src/generate.py --file path/to.json      # Конкретный файл
  python src/generate.py --max 3                  # Максимум 3 поста

Выход: data/drafts/YYYY-MM-DD.json
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

# Добавить корень проекта в path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / "config" / ".env")

from src.claude_client import filter_articles, generate_post, validate_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def find_latest_articles() -> Path:
    """Найти последний файл в data/articles/"""
    articles_dir = PROJECT_ROOT / "data" / "articles"
    files = sorted(articles_dir.glob("*.json"), reverse=True)
    if not files:
        raise FileNotFoundError("Нет файлов в data/articles/")
    return files[0]


def load_json(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Генерация постов PropTech Russia")
    parser.add_argument("--date", help="Дата файла статей (YYYY-MM-DD)")
    parser.add_argument("--file", help="Путь к файлу статей")
    parser.add_argument("--max", type=int, default=5, help="Максимум постов (default: 5)")
    args = parser.parse_args()

    # 1. Найти файл статей
    if args.file:
        articles_path = Path(args.file)
    elif args.date:
        articles_path = PROJECT_ROOT / "data" / "articles" / f"{args.date}.json"
    else:
        articles_path = find_latest_articles()

    logger.info("Загрузка статей из %s", articles_path)
    articles = load_json(articles_path)

    if not articles:
        logger.error("Файл пустой — нет статей для обработки")
        return

    logger.info("Загружено %d статей", len(articles))

    # 2. Фильтрация
    logger.info("Фильтрация статей через Claude...")
    selected = filter_articles(articles, max_select=args.max)
    logger.info("Прошли фильтр: %d статей", len(selected))

    for s in selected:
        logger.info("  + %s... — %s", s["id"][:8], s.get("reason", "no reason"))

    # 3. Найти полные статьи по id
    articles_by_id = {a["id"]: a for a in articles}
    selected_articles = []
    for s in selected:
        if s["id"] in articles_by_id:
            selected_articles.append(articles_by_id[s["id"]])
        else:
            logger.warning("Статья %s не найдена в articles — пропускаем", s["id"])

    if not selected_articles:
        logger.error("Ни одна статья не прошла фильтр")
        return

    # 4. Генерация постов
    drafts = []

    for i, article in enumerate(selected_articles):
        logger.info(
            "Генерация поста %d/%d: %s...",
            i + 1, len(selected_articles), article["title"][:60],
        )

        post_text = generate_post(article)

        if post_text is None:
            logger.error("Не удалось сгенерировать пост для: %s", article["title"][:60])
            continue

        word_count = len(post_text.split())

        draft = {
            "id": str(uuid.uuid4()),
            "source_article_id": article["id"],
            "post_text": post_text,
            "image_url": article.get("image_url"),
            "source_url": article["url"],
            "source_name": article["source_name"],
            "category": article.get("category_hint", "unknown"),
            "content_type": "youtube_review" if article["source_type"] == "youtube" else "news",
            "scheduled_date": date.today().isoformat(),
            "status": "draft",
            "word_count": word_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        drafts.append(draft)

    if not drafts:
        logger.error("Ни одного поста не сгенерировано")
        return

    # 5. Сохранить
    output_path = PROJECT_ROOT / "data" / "drafts" / f"{date.today().isoformat()}.json"
    save_json(drafts, output_path)
    logger.info("Сохранено %d черновиков в %s", len(drafts), output_path)

    # 6. Показать результат
    print(f"\n{'='*70}")
    print(f"  РЕЗУЛЬТАТ: {len(drafts)} черновиков")
    print(f"{'='*70}")

    for i, d in enumerate(drafts):
        # Финальная валидация для отчёта
        problems = validate_post(d["post_text"])

        status = "+" if not problems else "!"
        print(f"\n{'-'*70}")
        print(f"{status} ПОСТ {i+1} | {d['source_name'][:40]} | {d['word_count']} слов | {d['category']}")
        if problems:
            for p in problems:
                print(f"   ! {p}")
        print(f"{'-'*70}")
        print(d["post_text"])

    print(f"\n{'='*70}")
    print(f"Файл: {output_path}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
