# app/db/repositories/psychologist_content.py
# --- agent_meta ---
# role: psychologist-content-repository
# contract: CRUD-операции над таблицей psychologist_content (витрина/каталог)
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий для таблицы psychologist_content."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_all, fetch_one
from app.models.content_pipeline import PsychologistContent, PsychologistContentCreate


logger = logging.getLogger("vmeste.db.repositories.psychologist_content")

# Колонки таблицы psychologist_content
CONTENT_COLUMNS = (
    "content_id",
    "source_id",
    "doc_id",
    "title",
    "summary",
    "description",
    "content_type",
    "topic",
    "tags",
    "price",
    "currency",
    "url",
    "media_url",
    "thumbnail_url",
    "duration_minutes",
    "available",
    "metadata",
    "created_at",
    "updated_at",
    "is_deleted",
)


def list_available(limit: int = 5) -> list[dict[str, Any]]:
    """Возвращает список активных материалов с базовыми полями."""

    logger.debug("Загрузка материалов психолога, limit=%s", limit)
    query = """
        SELECT
            content_id,
            title,
            summary,
            url,
            topic,
            content_type,
            tags,
            price,
            currency,
            duration_minutes,
            metadata
        FROM psychologist_content
        WHERE available = TRUE
          AND is_deleted = FALSE
        ORDER BY updated_at DESC
        LIMIT %(limit)s
    """
    rows = fetch_all(query, {"limit": limit})
    return rows


def create(payload: PsychologistContentCreate) -> PsychologistContent:
    """Создаёт запись в psychologist_content (витрина).

    Args:
        payload: Данные для создания записи.

    Returns:
        Созданная запись PsychologistContent.

    Raises:
        RuntimeError: Если не удалось создать запись.
    """
    logger.info("Создание записи каталога: %s", payload.title)
    query = f"""
        INSERT INTO psychologist_content (
            doc_id, title, summary, description, content_type, topic,
            tags, price, currency, url, media_url, thumbnail_url,
            duration_minutes, available, metadata
        )
        VALUES (
            %(doc_id)s, %(title)s, %(summary)s, %(description)s, %(content_type)s, %(topic)s,
            %(tags)s, %(price)s, %(currency)s, %(url)s, %(media_url)s, %(thumbnail_url)s,
            %(duration_minutes)s, %(available)s, %(metadata)s
        )
        RETURNING {", ".join(CONTENT_COLUMNS)}
    """
    params = {
        "doc_id": payload.doc_id,
        "title": payload.title,
        "summary": payload.summary,
        "description": payload.description,
        "content_type": payload.content_type,
        "topic": payload.topic,
        "tags": Json(payload.tags),
        "price": payload.price,
        "currency": payload.currency,
        "url": payload.url,
        "media_url": payload.media_url,
        "thumbnail_url": payload.thumbnail_url,
        "duration_minutes": payload.duration_minutes,
        "available": payload.available,
        "metadata": Json(payload.metadata),
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать запись каталога"
        logger.error(msg)
        raise RuntimeError(msg)
    return PsychologistContent.model_validate(row)


def get_by_doc_id(doc_id: UUID) -> PsychologistContent | None:
    """Возвращает запись каталога по doc_id.

    Args:
        doc_id: UUID документа.

    Returns:
        PsychologistContent или None если не найден.
    """
    logger.debug("Поиск записи каталога по doc_id=%s", doc_id)
    query = f"""
        SELECT {", ".join(CONTENT_COLUMNS)}
        FROM psychologist_content
        WHERE doc_id = %(doc_id)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"doc_id": doc_id})
    return PsychologistContent.model_validate(row) if row else None


__all__ = [
    "list_available",
    "create",
    "get_by_doc_id",
]
