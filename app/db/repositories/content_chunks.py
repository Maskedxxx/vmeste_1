# app/db/repositories/content_chunks.py
# --- agent_meta ---
# role: content-chunks-repository
# contract: CRUD-операции над таблицей content_chunks
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий чанков контента для RAG."""

from __future__ import annotations

import logging
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_all, fetch_one, get_connection
from app.models.content_pipeline import ContentChunk, ContentChunkCreate


logger = logging.getLogger("vmeste.db.repositories.content_chunks")

# Колонки таблицы content_chunks
CHUNK_COLUMNS = (
    "chunk_id",
    "doc_id",
    "sequence",
    "text",
    "summary",
    "topic",
    "topic_conf",
    "tov_score",
    "content_type",
    "keywords",
    "cleaned",
    "metadata",
    "created_at",
    "updated_at",
    "is_deleted",
)


def create(payload: ContentChunkCreate) -> ContentChunk:
    """Создаёт один чанк и возвращает полную запись.

    Args:
        payload: Данные для создания чанка.

    Returns:
        Созданная запись ContentChunk.

    Raises:
        RuntimeError: Если не удалось создать запись.
    """
    logger.debug("Создание чанка seq=%d для doc_id=%s", payload.sequence, payload.doc_id)
    query = f"""
        INSERT INTO content_chunks (
            doc_id, sequence, text, summary, topic, topic_conf,
            tov_score, content_type, keywords, cleaned, metadata
        )
        VALUES (
            %(doc_id)s, %(sequence)s, %(text)s, %(summary)s, %(topic)s, %(topic_conf)s,
            %(tov_score)s, %(content_type)s, %(keywords)s, %(cleaned)s, %(metadata)s
        )
        RETURNING {", ".join(CHUNK_COLUMNS)}
    """
    params = {
        "doc_id": payload.doc_id,
        "sequence": payload.sequence,
        "text": payload.text,
        "summary": payload.summary,
        "topic": payload.topic,
        "topic_conf": payload.topic_conf,
        "tov_score": payload.tov_score,
        "content_type": payload.content_type,
        "keywords": Json(payload.keywords),
        "cleaned": payload.cleaned,
        "metadata": Json(payload.metadata),
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать чанк"
        logger.error(msg)
        raise RuntimeError(msg)
    return ContentChunk.model_validate(row)


def create_batch(payloads: list[ContentChunkCreate]) -> list[ContentChunk]:
    """Создаёт несколько чанков за одну транзакцию.

    Args:
        payloads: Список данных для создания чанков.

    Returns:
        Список созданных записей ContentChunk.
    """
    if not payloads:
        return []

    logger.info("Создание %d чанков для doc_id=%s", len(payloads), payloads[0].doc_id)

    query = f"""
        INSERT INTO content_chunks (
            doc_id, sequence, text, summary, topic, topic_conf,
            tov_score, content_type, keywords, cleaned, metadata
        )
        VALUES (
            %(doc_id)s, %(sequence)s, %(text)s, %(summary)s, %(topic)s, %(topic_conf)s,
            %(tov_score)s, %(content_type)s, %(keywords)s, %(cleaned)s, %(metadata)s
        )
        RETURNING {", ".join(CHUNK_COLUMNS)}
    """

    results: list[ContentChunk] = []
    with get_connection() as conn:
        # Выключаем autocommit для батча
        with conn.cursor() as cursor:
            for payload in payloads:
                params = {
                    "doc_id": payload.doc_id,
                    "sequence": payload.sequence,
                    "text": payload.text,
                    "summary": payload.summary,
                    "topic": payload.topic,
                    "topic_conf": payload.topic_conf,
                    "tov_score": payload.tov_score,
                    "content_type": payload.content_type,
                    "keywords": Json(payload.keywords),
                    "cleaned": payload.cleaned,
                    "metadata": Json(payload.metadata),
                }
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row:
                    # Преобразуем tuple в dict
                    row_dict = dict(zip(CHUNK_COLUMNS, row))
                    results.append(ContentChunk.model_validate(row_dict))

    logger.info("Создано %d чанков", len(results))
    return results


def get_by_id(chunk_id: UUID) -> ContentChunk | None:
    """Возвращает чанк по ID.

    Args:
        chunk_id: UUID чанка.

    Returns:
        ContentChunk или None если не найден.
    """
    logger.debug("Поиск чанка chunk_id=%s", chunk_id)
    query = f"""
        SELECT {", ".join(CHUNK_COLUMNS)}
        FROM content_chunks
        WHERE chunk_id = %(chunk_id)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"chunk_id": chunk_id})
    return ContentChunk.model_validate(row) if row else None


def list_by_doc_id(doc_id: UUID) -> list[ContentChunk]:
    """Возвращает все чанки документа.

    Args:
        doc_id: UUID документа.

    Returns:
        Список чанков, отсортированных по sequence.
    """
    logger.debug("Загрузка чанков для doc_id=%s", doc_id)
    query = f"""
        SELECT {", ".join(CHUNK_COLUMNS)}
        FROM content_chunks
        WHERE doc_id = %(doc_id)s AND is_deleted = FALSE
        ORDER BY sequence
    """
    rows = fetch_all(query, {"doc_id": doc_id})
    return [ContentChunk.model_validate(row) for row in rows]


def count_by_doc_id(doc_id: UUID) -> int:
    """Возвращает количество чанков документа.

    Args:
        doc_id: UUID документа.

    Returns:
        Количество чанков.
    """
    query = """
        SELECT COUNT(*) as cnt FROM content_chunks
        WHERE doc_id = %(doc_id)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"doc_id": doc_id})
    return row["cnt"] if row else 0


__all__ = [
    "create",
    "create_batch",
    "get_by_id",
    "list_by_doc_id",
    "count_by_doc_id",
]
