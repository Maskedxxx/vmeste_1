# app/models/content_pipeline.py
# --- agent_meta ---
# role: content-pipeline-models
# contract: Pydantic модели для пайплайна загрузки контента психолога
# owner: backend-core
# --- /agent_meta ---

"""
Модели для пайплайна загрузки контента.

Включает:
- ContentInput — входные данные из JSON файла
- Source, Document, ContentChunk, ChunkEmbeddingMeta — записи в БД
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# Типы контента и тем
TopicType = Literal["body", "mind", "sex"]
ContentType = Literal["lesson", "webinar", "article", "course", "consultation"]
SourceType = Literal["video", "podcast", "post", "article", "document", "lesson"]


# -----------------------------------------------------------------------------
# Входные данные (из JSON файла)
# -----------------------------------------------------------------------------

class SourceInput(BaseModel):
    """Данные источника (провайдера) из JSON файла.

    Attributes:
        source_type: Тип провайдера (manual, yandex_disk, google_drive и т.д.).
        title: Название источника.
        url: Ссылка на источник (опционально).
    """
    source_type: str = Field(default="manual")
    title: str = Field(default="Ручной ввод")
    url: str | None = None


class ContentInput(BaseModel):
    """Входные данные одного материала из JSON файла.

    Attributes:
        slug: Уникальный human-readable идентификатор для проверки дубликатов.
        title: Заголовок материала.
        url: Ссылка на оригинал (опционально).
        topic: Тема контента (body/mind/sex).
        content_type: Тип для каталога (lesson/webinar/article/course/consultation).
        tags: Теги для фильтрации.
        price: Стоимость материала (опционально).
        currency: Валюта (по умолчанию RUB).
        summary: Краткое описание для превью.
        description: Полное описание для каталога.
        full_text: Полный текст для RAG (разбивается на чанки).
    """
    slug: str = Field(..., min_length=1, description="Уникальный идентификатор")
    title: str = Field(..., min_length=1)
    url: str | None = None
    topic: TopicType
    content_type: ContentType = Field(default="lesson")
    tags: list[str] = Field(default_factory=list)
    price: float | None = None
    currency: str = "RUB"
    summary: str | None = None
    description: str | None = None
    full_text: str = Field(..., min_length=10, description="Текст для RAG")


class ContentInputBatch(BaseModel):
    """Пакет входных данных (корневой объект JSON файла).

    Attributes:
        source: Данные источника (опционально, по умолчанию manual).
        content: Список материалов.
    """
    source: SourceInput | None = None
    content: list[ContentInput]


# -----------------------------------------------------------------------------
# Модели БД: sources
# -----------------------------------------------------------------------------

class Source(BaseModel):
    """Запись в таблице sources."""
    source_id: UUID
    source_type: str
    title: str
    url: str | None
    meta: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class SourceCreate(BaseModel):
    """Данные для создания записи в sources."""
    source_type: str
    title: str
    url: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Модели БД: documents
# -----------------------------------------------------------------------------

class Document(BaseModel):
    """Запись в таблице documents."""
    doc_id: UUID
    source_id: UUID
    slug: str | None
    title: str | None
    raw_text: str
    storage_path: str | None
    status: str
    meta: dict[str, Any]
    checksum: str | None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class DocumentCreate(BaseModel):
    """Данные для создания записи в documents."""
    source_id: UUID
    slug: str | None = None
    title: str | None = None
    raw_text: str
    storage_path: str | None = None
    status: str = "raw"
    meta: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None


# -----------------------------------------------------------------------------
# Модели БД: content_chunks
# -----------------------------------------------------------------------------

class ContentChunk(BaseModel):
    """Запись в таблице content_chunks."""
    chunk_id: UUID
    doc_id: UUID
    sequence: int
    text: str
    summary: str | None
    topic: str | None
    topic_conf: float | None
    tov_score: float | None
    content_type: str | None
    keywords: list[str]
    cleaned: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class ContentChunkCreate(BaseModel):
    """Данные для создания записи в content_chunks."""
    doc_id: UUID
    sequence: int
    text: str
    summary: str | None = None
    topic: str | None = None
    topic_conf: float | None = None
    tov_score: float | None = None
    content_type: str | None = None
    keywords: list[str] = Field(default_factory=list)
    cleaned: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Модели БД: chunk_embeddings_meta
# -----------------------------------------------------------------------------

class ChunkEmbeddingMeta(BaseModel):
    """Запись в таблице chunk_embeddings_meta."""
    embedding_id: UUID
    chunk_id: UUID
    collection_name: str
    embedding_provider: str
    embedding_dim: int
    indexed_at: datetime
    needs_sync: bool = False
    metadata: dict[str, Any]
    is_deleted: bool = False


class ChunkEmbeddingMetaCreate(BaseModel):
    """Данные для создания записи в chunk_embeddings_meta."""
    embedding_id: UUID
    chunk_id: UUID
    collection_name: str
    embedding_provider: str
    embedding_dim: int
    indexed_at: datetime | None = None
    needs_sync: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Модели БД: psychologist_content (каталог/витрина)
# -----------------------------------------------------------------------------

class PsychologistContent(BaseModel):
    """Запись в таблице psychologist_content (витрина)."""
    content_id: UUID
    source_id: UUID | None
    doc_id: UUID | None
    title: str
    summary: str | None
    description: str | None
    content_type: str
    topic: str | None
    tags: list[str]
    price: float | None
    currency: str | None
    url: str | None
    media_url: str | None
    thumbnail_url: str | None
    duration_minutes: int | None
    available: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class PsychologistContentCreate(BaseModel):
    """Данные для создания записи в psychologist_content."""
    doc_id: UUID | None = None
    title: str
    summary: str | None = None
    description: str | None = None
    content_type: str
    topic: str | None = None
    tags: list[str] = Field(default_factory=list)
    price: float | None = None
    currency: str = "RUB"
    url: str | None = None
    media_url: str | None = None
    thumbnail_url: str | None = None
    duration_minutes: int | None = None
    available: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Результат работы пайплайна
# -----------------------------------------------------------------------------

class PipelineResult(BaseModel):
    """Результат обработки одного материала."""
    slug: str
    source_id: UUID | None = None
    content_id: UUID | None = None
    doc_id: UUID | None = None
    chunks_count: int = 0
    embeddings_count: int = 0
    success: bool = True
    error: str | None = None


class PipelineBatchResult(BaseModel):
    """Результат обработки пакета материалов."""
    total: int = 0
    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[PipelineResult] = Field(default_factory=list)


__all__ = [
    # Типы
    "TopicType",
    "ContentType",
    "SourceType",
    # Входные данные
    "SourceInput",
    "ContentInput",
    "ContentInputBatch",
    # Модели БД
    "Source",
    "SourceCreate",
    "Document",
    "DocumentCreate",
    "ContentChunk",
    "ContentChunkCreate",
    "ChunkEmbeddingMeta",
    "ChunkEmbeddingMetaCreate",
    "PsychologistContent",
    "PsychologistContentCreate",
    # Результаты
    "PipelineResult",
    "PipelineBatchResult",
]
