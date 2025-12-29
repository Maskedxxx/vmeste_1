# seed_psychologist_content.py
# --- agent_meta ---
# role: seed-script
# contract: загружает тестовые материалы psychologist_content из JSON
# owner: backend-core
# --- /agent_meta ---

"""Временный скрипт для восстановления psychologist_content."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from app.db.connection import execute


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
logger = logging.getLogger("vmeste.seed.psychologist_content")

DATA_PATH = Path(__file__).parent / "data" / "test_data" / "test_data.json"


def load_records() -> list[dict[str, Any]]:
    """Загружает массив psychologist_content из JSON."""

    if not DATA_PATH.exists():  # pragma: no cover
        raise FileNotFoundError(f"Не найден файл с тестовыми данными: {DATA_PATH}")
    with DATA_PATH.open(encoding="utf-8") as fp:
        payload = json.load(fp)
    records = payload.get("psychologist_content")
    if not records:
        raise ValueError("В test_data.json отсутствует ключ psychologist_content")
    logger.info("Загружено %s записей из %s", len(records), DATA_PATH)
    return records


def truncate_table() -> None:
    """Очищает таблицу psychologist_content перед вставкой."""

    logger.info("Очищаю таблицу psychologist_content")
    execute("TRUNCATE TABLE psychologist_content RESTART IDENTITY CASCADE;")


def insert_records(records: list[dict[str, Any]]) -> int:
    """Вставляет записи в таблицу psychologist_content."""

    query = """
        INSERT INTO psychologist_content (
            source_id,
            title,
            summary,
            description,
            content_type,
            topic,
            tags,
            price,
            currency,
            url,
            media_url,
            thumbnail_url,
            duration_minutes,
            available,
            metadata
        ) VALUES (
            %(source_id)s,
            %(title)s,
            %(summary)s,
            %(description)s,
            %(content_type)s,
            %(topic)s,
            %(tags)s,
            %(price)s,
            %(currency)s,
            %(url)s,
            %(media_url)s,
            %(thumbnail_url)s,
            %(duration_minutes)s,
            %(available)s,
            %(metadata)s
        );
    """

    inserted = 0
    for record in records:
        payload = {
            "source_id": record.get("source_id"),
            "title": record["title"],
            "summary": record.get("summary"),
            "description": record.get("description"),
            "content_type": record["content_type"],
            "topic": record.get("topic"),
            "tags": Json(record.get("tags", [])),
            "price": record.get("price"),
            "currency": record.get("currency", "RUB"),
            "url": record.get("url"),
            "media_url": record.get("media_url"),
            "thumbnail_url": record.get("thumbnail_url"),
            "duration_minutes": record.get("duration_minutes"),
            "available": record.get("available", True),
            "metadata": Json(record.get("metadata", {})),
        }
        execute(query, payload)
        inserted += 1
    return inserted


def main() -> None:
    """Точка входа скрипта."""

    records = load_records()
    truncate_table()
    inserted = insert_records(records)
    logger.info("Добавлено %s записей psychologist_content", inserted)


if __name__ == "__main__":
    main()
