# app/db/repositories/documents.py
# --- agent_meta ---
# role: documents-repository
# contract: CRUD-операции над таблицей documents
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий документов (сырой текст для RAG)."""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_one
from app.models.content_pipeline import Document, DocumentCreate


logger = logging.getLogger("vmeste.db.repositories.documents")

# Колонки таблицы documents
DOCUMENT_COLUMNS = (
    "doc_id",
    "source_id",
    "slug",
    "title",
    "raw_text",
    "storage_path",
    "status",
    "meta",
    "checksum",
    "created_at",
    "updated_at",
    "is_deleted",
)


def compute_checksum(text: str) -> str:
    """Вычисляет SHA256 хеш текста.

    Args:
        text: Исходный текст.

    Returns:
        Hex-строка SHA256 хеша.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create(payload: DocumentCreate) -> Document:
    """Создаёт запись в documents и возвращает полную запись.

    Если checksum не указан, вычисляется автоматически из raw_text.

    Args:
        payload: Данные для создания документа.

    Returns:
        Созданная запись Document.

    Raises:
        RuntimeError: Если не удалось создать запись.
    """
    # Вычисляем checksum если не указан
    checksum = payload.checksum or compute_checksum(payload.raw_text)

    logger.info("Создание документа slug=%s, title=%s", payload.slug, payload.title)
    query = f"""
        INSERT INTO documents (source_id, slug, title, raw_text, storage_path, status, meta, checksum)
        VALUES (%(source_id)s, %(slug)s, %(title)s, %(raw_text)s, %(storage_path)s, %(status)s, %(meta)s, %(checksum)s)
        RETURNING {", ".join(DOCUMENT_COLUMNS)}
    """
    params = {
        "source_id": payload.source_id,
        "slug": payload.slug,
        "title": payload.title,
        "raw_text": payload.raw_text,
        "storage_path": payload.storage_path,
        "status": payload.status,
        "meta": Json(payload.meta),
        "checksum": checksum,
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать документ"
        logger.error(msg)
        raise RuntimeError(msg)
    return Document.model_validate(row)


def get_by_id(doc_id: UUID) -> Document | None:
    """Возвращает документ по ID.

    Args:
        doc_id: UUID документа.

    Returns:
        Document или None если не найден.
    """
    logger.debug("Поиск документа doc_id=%s", doc_id)
    query = f"""
        SELECT {", ".join(DOCUMENT_COLUMNS)}
        FROM documents
        WHERE doc_id = %(doc_id)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"doc_id": doc_id})
    return Document.model_validate(row) if row else None


def get_by_source_id(source_id: UUID) -> Document | None:
    """Возвращает документ по source_id.

    Args:
        source_id: UUID источника.

    Returns:
        Document или None если не найден.
    """
    logger.debug("Поиск документа по source_id=%s", source_id)
    query = f"""
        SELECT {", ".join(DOCUMENT_COLUMNS)}
        FROM documents
        WHERE source_id = %(source_id)s AND is_deleted = FALSE
        ORDER BY created_at DESC
        LIMIT 1
    """
    row = fetch_one(query, {"source_id": source_id})
    return Document.model_validate(row) if row else None


def exists_by_checksum(checksum: str) -> bool:
    """Проверяет существует ли документ с указанным checksum.

    Args:
        checksum: SHA256 хеш текста.

    Returns:
        True если документ существует.
    """
    logger.debug("Проверка существования checksum=%s", checksum[:16])
    query = """
        SELECT 1 FROM documents
        WHERE checksum = %(checksum)s AND is_deleted = FALSE
        LIMIT 1
    """
    row = fetch_one(query, {"checksum": checksum})
    return row is not None


def exists_by_slug(slug: str) -> bool:
    """Проверяет существует ли документ с указанным slug.

    Args:
        slug: Уникальный идентификатор материала.

    Returns:
        True если документ существует.
    """
    logger.debug("Проверка существования slug=%s", slug)
    query = """
        SELECT 1 FROM documents
        WHERE slug = %(slug)s AND is_deleted = FALSE
        LIMIT 1
    """
    row = fetch_one(query, {"slug": slug})
    return row is not None


def get_by_slug(slug: str) -> Document | None:
    """Возвращает документ по slug.

    Args:
        slug: Уникальный идентификатор материала.

    Returns:
        Document или None если не найден.
    """
    logger.debug("Поиск документа по slug=%s", slug)
    query = f"""
        SELECT {", ".join(DOCUMENT_COLUMNS)}
        FROM documents
        WHERE slug = %(slug)s AND is_deleted = FALSE
    """
    row = fetch_one(query, {"slug": slug})
    return Document.model_validate(row) if row else None


__all__ = [
    "compute_checksum",
    "create",
    "get_by_id",
    "get_by_source_id",
    "exists_by_checksum",
    "exists_by_slug",
    "get_by_slug",
]
