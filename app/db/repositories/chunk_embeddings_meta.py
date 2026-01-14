# app/db/repositories/chunk_embeddings_meta.py
# --- agent_meta ---
# role: chunk-embeddings-meta-repository
# contract: CRUD-операции над таблицей chunk_embeddings_meta
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий метаданных эмбеддингов в ChromaDB."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_all, fetch_one, get_connection
from app.models.content_pipeline import ChunkEmbeddingMeta, ChunkEmbeddingMetaCreate


logger = logging.getLogger("vmeste.db.repositories.chunk_embeddings_meta")

# Колонки таблицы chunk_embeddings_meta
META_COLUMNS = (
    "embedding_id",
    "chunk_id",
    "collection_name",
    "embedding_provider",
    "embedding_dim",
    "indexed_at",
    "needs_sync",
    "metadata",
    "is_deleted",
)


def create(payload: ChunkEmbeddingMetaCreate) -> ChunkEmbeddingMeta:
    """Создаёт запись метаданных эмбеддинга.

    Args:
        payload: Данные для создания записи.

    Returns:
        Созданная запись ChunkEmbeddingMeta.

    Raises:
        RuntimeError: Если не удалось создать запись.
    """
    indexed_at = payload.indexed_at or datetime.now(timezone.utc)

    logger.debug("Создание метаданных эмбеддинга для chunk_id=%s", payload.chunk_id)
    query = f"""
        INSERT INTO chunk_embeddings_meta (
            embedding_id, chunk_id, collection_name, embedding_provider,
            embedding_dim, indexed_at, needs_sync, metadata
        )
        VALUES (
            %(embedding_id)s, %(chunk_id)s, %(collection_name)s, %(embedding_provider)s,
            %(embedding_dim)s, %(indexed_at)s, %(needs_sync)s, %(metadata)s
        )
        RETURNING {", ".join(META_COLUMNS)}
    """
    params = {
        "embedding_id": payload.embedding_id,
        "chunk_id": payload.chunk_id,
        "collection_name": payload.collection_name,
        "embedding_provider": payload.embedding_provider,
        "embedding_dim": payload.embedding_dim,
        "indexed_at": indexed_at,
        "needs_sync": payload.needs_sync,
        "metadata": Json(payload.metadata),
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать метаданные эмбеддинга"
        logger.error(msg)
        raise RuntimeError(msg)
    return ChunkEmbeddingMeta.model_validate(row)


def create_batch(payloads: list[ChunkEmbeddingMetaCreate]) -> list[ChunkEmbeddingMeta]:
    """Создаёт несколько записей метаданных за одну транзакцию.

    Args:
        payloads: Список данных для создания записей.

    Returns:
        Список созданных записей ChunkEmbeddingMeta.
    """
    if not payloads:
        return []

    logger.info("Создание %d записей метаданных эмбеддингов", len(payloads))

    query = f"""
        INSERT INTO chunk_embeddings_meta (
            embedding_id, chunk_id, collection_name, embedding_provider,
            embedding_dim, indexed_at, needs_sync, metadata
        )
        VALUES (
            %(embedding_id)s, %(chunk_id)s, %(collection_name)s, %(embedding_provider)s,
            %(embedding_dim)s, %(indexed_at)s, %(needs_sync)s, %(metadata)s
        )
        RETURNING {", ".join(META_COLUMNS)}
    """

    results: list[ChunkEmbeddingMeta] = []
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            for payload in payloads:
                indexed_at = payload.indexed_at or now
                params = {
                    "embedding_id": payload.embedding_id,
                    "chunk_id": payload.chunk_id,
                    "collection_name": payload.collection_name,
                    "embedding_provider": payload.embedding_provider,
                    "embedding_dim": payload.embedding_dim,
                    "indexed_at": indexed_at,
                    "needs_sync": payload.needs_sync,
                    "metadata": Json(payload.metadata),
                }
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row:
                    row_dict = dict(zip(META_COLUMNS, row))
                    results.append(ChunkEmbeddingMeta.model_validate(row_dict))

    logger.info("Создано %d записей метаданных", len(results))
    return results


def get_by_chunk_id(chunk_id: UUID, collection_name: str) -> ChunkEmbeddingMeta | None:
    """Возвращает метаданные эмбеддинга по chunk_id и коллекции.

    Args:
        chunk_id: UUID чанка.
        collection_name: Имя коллекции ChromaDB.

    Returns:
        ChunkEmbeddingMeta или None если не найден.
    """
    logger.debug("Поиск метаданных для chunk_id=%s, collection=%s", chunk_id, collection_name)
    query = f"""
        SELECT {", ".join(META_COLUMNS)}
        FROM chunk_embeddings_meta
        WHERE chunk_id = %(chunk_id)s
          AND collection_name = %(collection_name)s
          AND is_deleted = FALSE
    """
    row = fetch_one(query, {"chunk_id": chunk_id, "collection_name": collection_name})
    return ChunkEmbeddingMeta.model_validate(row) if row else None


def list_by_chunk_ids(chunk_ids: list[UUID], collection_name: str) -> list[ChunkEmbeddingMeta]:
    """Возвращает метаданные для списка чанков.

    Args:
        chunk_ids: Список UUID чанков.
        collection_name: Имя коллекции ChromaDB.

    Returns:
        Список ChunkEmbeddingMeta.
    """
    if not chunk_ids:
        return []

    logger.debug("Загрузка метаданных для %d чанков", len(chunk_ids))
    # Используем ANY для списка UUID
    query = f"""
        SELECT {", ".join(META_COLUMNS)}
        FROM chunk_embeddings_meta
        WHERE chunk_id = ANY(%(chunk_ids)s)
          AND collection_name = %(collection_name)s
          AND is_deleted = FALSE
    """
    rows = fetch_all(query, {"chunk_ids": chunk_ids, "collection_name": collection_name})
    return [ChunkEmbeddingMeta.model_validate(row) for row in rows]


def mark_needs_sync(chunk_ids: list[UUID], collection_name: str) -> int:
    """Помечает эмбеддинги как требующие синхронизации.

    Args:
        chunk_ids: Список UUID чанков.
        collection_name: Имя коллекции ChromaDB.

    Returns:
        Количество обновлённых записей.
    """
    if not chunk_ids:
        return 0

    logger.info("Пометка %d эмбеддингов для синхронизации", len(chunk_ids))
    query = """
        UPDATE chunk_embeddings_meta
        SET needs_sync = TRUE
        WHERE chunk_id = ANY(%(chunk_ids)s)
          AND collection_name = %(collection_name)s
          AND is_deleted = FALSE
    """
    # Используем execute и возвращаем количество
    from app.db.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, {"chunk_ids": chunk_ids, "collection_name": collection_name})
            return cursor.rowcount


__all__ = [
    "create",
    "create_batch",
    "get_by_chunk_id",
    "list_by_chunk_ids",
    "mark_needs_sync",
]
