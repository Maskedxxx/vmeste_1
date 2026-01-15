# app/db/repositories/sources.py
# --- agent_meta ---
# role: sources-repository
# contract: CRUD-операции над таблицей sources (провайдеры данных)
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий провайдеров данных (sources).

Таблица sources хранит провайдеры данных (откуда пришёл контент):
- manual — ручной ввод через JSON
- yandex_disk — импорт с Яндекс Диска
- google_drive — импорт с Google Drive
- и т.д.

Каждый документ (documents) ссылается на источник-провайдер.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_one
from app.models.content_pipeline import Source, SourceCreate


logger = logging.getLogger("vmeste.db.repositories.sources")

# Колонки таблицы sources
SOURCE_COLUMNS = (
    "source_id",
    "source_type",
    "title",
    "url",
    "meta",
    "created_at",
    "updated_at",
    "is_deleted",
)


def create(payload: SourceCreate) -> Source:
    """Создаёт запись в sources и возвращает полную запись.

    Args:
        payload: Данные для создания источника.

    Returns:
        Созданная запись Source.

    Raises:
        RuntimeError: Если не удалось создать запись.
    """
    logger.info("Создание источника: %s", payload.title)
    query = f"""
        INSERT INTO sources (source_type, title, url, meta)
        VALUES (%(source_type)s, %(title)s, %(url)s, %(meta)s)
        RETURNING {", ".join(SOURCE_COLUMNS)}
    """
    params = {
        "source_type": payload.source_type,
        "title": payload.title,
        "url": payload.url,
        "meta": Json(payload.meta),
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать источник"
        logger.error(msg)
        raise RuntimeError(msg)
    return Source.model_validate(row)


def get_by_id(source_id: UUID) -> Source | None:
    """Возвращает источник по ID.

    Args:
        source_id: UUID источника.

    Returns:
        Source или None если не найден.
    """
    logger.debug("Поиск источника source_id=%s", source_id)
    query = f"""
        SELECT {", ".join(SOURCE_COLUMNS)}
        FROM sources
        WHERE source_id = %(source_id)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"source_id": source_id})
    return Source.model_validate(row) if row else None


def get_by_type(source_type: str) -> Source | None:
    """Возвращает провайдер по типу.

    Args:
        source_type: Тип провайдера (manual, yandex_disk, google_drive...).

    Returns:
        Source или None если не найден.
    """
    logger.debug("Поиск провайдера source_type=%s", source_type)
    query = f"""
        SELECT {", ".join(SOURCE_COLUMNS)}
        FROM sources
        WHERE source_type = %(source_type)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"source_type": source_type})
    return Source.model_validate(row) if row else None


__all__ = [
    "create",
    "get_by_id",
    "get_by_type",
]
