# app/services/content_pipeline.py
# --- agent_meta ---
# role: content-pipeline-service
# contract: пайплайн загрузки контента психолога в PostgreSQL и ChromaDB
# owner: backend-core
# --- /agent_meta ---

"""
Пайплайн загрузки контента психолога.

Выполняет полную цепочку:
1. Валидация входных данных (проверка дубликатов по documents.slug)
2. Создание записи в documents (сырой текст + slug + title)
3. Создание записи в psychologist_content (витрина, связь через doc_id)
4. Нарезка на чанки → content_chunks
5. Генерация эмбеддингов → ChromaDB + chunk_embeddings_meta

Таблица sources теперь хранит провайдеров данных (manual, yandex_disk, и т.д.),
а не отдельные материалы.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import chromadb
from openai import OpenAI

from app.db.repositories import (
    chunk_embeddings_meta,
    content_chunks,
    documents,
    psychologist_content,
    sources,
)
from app.models.content_pipeline import (
    ChunkEmbeddingMetaCreate,
    ContentChunkCreate,
    ContentInput,
    DocumentCreate,
    PipelineBatchResult,
    PipelineResult,
    PsychologistContentCreate,
    SourceCreate,
    SourceInput,
)


logger = logging.getLogger("vmeste.services.content_pipeline")

# Константы
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072
COLLECTION_NAME = "content_all"
CHUNK_SIZE_TARGET = 700
DEFAULT_SOURCE_TYPE = "manual"


class ContentPipeline:
    """Пайплайн загрузки контента в PostgreSQL и ChromaDB.

    Attributes:
        chroma_client: Клиент ChromaDB.
        openai_client: Клиент OpenAI для генерации эмбеддингов.
        collection: Коллекция ChromaDB для хранения чанков.
        source_id: UUID провайдера данных.
    """

    def __init__(
        self,
        *,
        chroma_host: str | None = None,
        chroma_port: int | None = None,
        collection_name: str = COLLECTION_NAME,
        openai_client: OpenAI | None = None,
        source_input: SourceInput | None = None,
    ) -> None:
        """Инициализирует пайплайн.

        Args:
            chroma_host: Хост ChromaDB (по умолчанию из env CHROMA_HOST).
            chroma_port: Порт ChromaDB (по умолчанию из env CHROMA_PORT).
            collection_name: Имя коллекции ChromaDB.
            openai_client: Клиент OpenAI (создаётся автоматически если не указан).
            source_input: Данные источника из JSON (опционально).
        """
        # Получаем или создаём провайдер данных
        if source_input is None:
            source_input = SourceInput()  # manual по умолчанию
        self.source_id = self._get_or_create_source(source_input)

        # ChromaDB
        host = chroma_host or os.getenv("CHROMA_HOST", "localhost")
        port = chroma_port or int(os.getenv("CHROMA_PORT", "8001"))
        self.chroma_client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "description": "RAG контент психолога"},
        )
        self.collection_name = collection_name
        logger.info("ChromaDB подключён: %s:%s, коллекция: %s", host, port, collection_name)

        # OpenAI
        self.openai_client = openai_client or OpenAI()
        logger.info("OpenAI клиент инициализирован")

    def _get_or_create_source(self, source_input: SourceInput) -> UUID:
        """Находит или создаёт провайдер данных.

        Args:
            source_input: Данные источника из JSON.

        Returns:
            UUID провайдера.
        """
        # Проверяем существует ли провайдер с таким типом
        existing = sources.get_by_type(source_input.source_type)
        if existing:
            logger.info(
                "Найден провайдер: %s (source_id=%s)",
                source_input.source_type,
                existing.source_id,
            )
            return existing.source_id

        # Создаём нового провайдера
        payload = SourceCreate(
            source_type=source_input.source_type,
            title=source_input.title,
            url=source_input.url,
            meta={"created_from_json": True},
        )
        source = sources.create(payload)
        logger.info(
            "Создан провайдер: %s (source_id=%s)",
            source_input.source_type,
            source.source_id,
        )
        return source.source_id

    # -------------------------------------------------------------------------
    # Валидация
    # -------------------------------------------------------------------------

    def check_duplicate(self, slug: str) -> bool:
        """Проверяет существует ли материал с указанным slug.

        Args:
            slug: Human-readable идентификатор.

        Returns:
            True если материал уже существует.
        """
        return documents.exists_by_slug(slug)

    # -------------------------------------------------------------------------
    # Шаг 1: documents
    # -------------------------------------------------------------------------

    def create_document(self, input_data: ContentInput) -> UUID:
        """Создаёт запись в таблице documents.

        Args:
            input_data: Входные данные материала.

        Returns:
            UUID созданного документа.
        """
        payload = DocumentCreate(
            source_id=self.source_id,
            slug=input_data.slug,
            title=input_data.title,
            raw_text=input_data.full_text,
            status="raw",
            meta={"topic": input_data.topic},
        )
        document = documents.create(payload)
        logger.info("Создан документ: %s (slug=%s)", document.doc_id, input_data.slug)
        return document.doc_id

    # -------------------------------------------------------------------------
    # Шаг 2: psychologist_content (витрина)
    # -------------------------------------------------------------------------

    def create_catalog_entry(self, input_data: ContentInput, doc_id: UUID) -> UUID:
        """Создаёт запись в таблице psychologist_content.

        Args:
            input_data: Входные данные материала.
            doc_id: UUID документа.

        Returns:
            UUID созданной записи каталога.
        """
        payload = PsychologistContentCreate(
            doc_id=doc_id,
            title=input_data.title,
            summary=input_data.summary,
            description=input_data.description,
            content_type=input_data.content_type,
            topic=input_data.topic,
            tags=input_data.tags,
            price=input_data.price,
            currency=input_data.currency,
            url=input_data.url,
        )
        content = psychologist_content.create(payload)
        logger.info("Создана запись каталога: %s", content.content_id)
        return content.content_id

    # -------------------------------------------------------------------------
    # Шаг 3: Нарезка на чанки
    # -------------------------------------------------------------------------

    def chunk_text(self, text: str, chunk_size: int = CHUNK_SIZE_TARGET) -> list[str]:
        """Разбивает текст на чанки по границам предложений.

        Args:
            text: Исходный текст.
            chunk_size: Целевой размер чанка в символах.

        Returns:
            Список текстов чанков.
        """
        # Разбиваем на предложения
        sentences: list[str] = []
        current_sentence = ""

        for char in text:
            current_sentence += char
            if char in ".!?" and len(current_sentence) > 10:
                sentences.append(current_sentence.strip())
                current_sentence = ""

        if current_sentence.strip():
            sentences.append(current_sentence.strip())

        # Формируем чанки
        chunks: list[str] = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def create_chunks(
        self,
        doc_id: UUID,
        chunk_texts: list[str],
        topic: str,
        content_type: str,
    ) -> list[UUID]:
        """Создаёт записи в таблице content_chunks.

        Args:
            doc_id: UUID документа.
            chunk_texts: Список текстов чанков.
            topic: Тема контента.
            content_type: Тип контента.

        Returns:
            Список UUID созданных чанков.
        """
        payloads = [
            ContentChunkCreate(
                doc_id=doc_id,
                sequence=i,
                text=text,
                topic=topic,
                content_type=content_type,
            )
            for i, text in enumerate(chunk_texts)
        ]
        chunks = content_chunks.create_batch(payloads)
        logger.info("Создано %d чанков для документа %s", len(chunks), doc_id)
        return [c.chunk_id for c in chunks]

    # -------------------------------------------------------------------------
    # Шаг 4: Эмбеддинги
    # -------------------------------------------------------------------------

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Генерирует эмбеддинги через OpenAI.

        Args:
            texts: Список текстов для эмбеддинга.

        Returns:
            Список векторов эмбеддингов.
        """
        if not texts:
            return []

        logger.info("Генерация %d эмбеддингов...", len(texts))
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def store_embeddings(
        self,
        chunk_ids: list[UUID],
        texts: list[str],
        embeddings: list[list[float]],
        source_id: UUID,
        topic: str,
    ) -> int:
        """Сохраняет эмбеддинги в ChromaDB и метаданные в PostgreSQL.

        Args:
            chunk_ids: Список UUID чанков.
            texts: Список текстов чанков.
            embeddings: Список векторов эмбеддингов.
            source_id: UUID источника.
            topic: Тема контента.

        Returns:
            Количество сохранённых эмбеддингов.
        """
        if not chunk_ids:
            return 0

        # Подготовка данных для ChromaDB
        ids = [str(chunk_id) for chunk_id in chunk_ids]
        metadatas = [
            {
                "source_id": str(source_id),
                "topic": topic,
                "chunk_index": i,
            }
            for i in range(len(chunk_ids))
        ]

        # Сохранение в ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("Сохранено %d эмбеддингов в ChromaDB", len(ids))

        # Сохранение метаданных в PostgreSQL
        now = datetime.now(timezone.utc)
        meta_payloads = [
            ChunkEmbeddingMetaCreate(
                embedding_id=chunk_id,  # используем chunk_id как embedding_id
                chunk_id=chunk_id,
                collection_name=self.collection_name,
                embedding_provider="openai",
                embedding_dim=EMBEDDING_DIM,
                indexed_at=now,
                metadata={"model": EMBEDDING_MODEL},
            )
            for chunk_id in chunk_ids
        ]
        chunk_embeddings_meta.create_batch(meta_payloads)
        logger.info("Сохранено %d записей метаданных в PostgreSQL", len(meta_payloads))

        return len(ids)

    # -------------------------------------------------------------------------
    # Главный метод: обработка одного материала
    # -------------------------------------------------------------------------

    def process(self, input_data: ContentInput) -> PipelineResult:
        """Выполняет полный пайплайн для одного материала.

        Args:
            input_data: Входные данные материала.

        Returns:
            Результат обработки PipelineResult.
        """
        result = PipelineResult(slug=input_data.slug)

        try:
            # Проверка дубликата
            if self.check_duplicate(input_data.slug):
                logger.warning("Пропуск дубликата: %s", input_data.slug)
                result.success = False
                result.error = "duplicate"
                return result

            # Шаг 1: documents (с slug и title)
            doc_id = self.create_document(input_data)
            result.doc_id = doc_id

            # Шаг 2: psychologist_content (связь через doc_id)
            content_id = self.create_catalog_entry(input_data, doc_id)
            result.content_id = content_id

            # Шаг 3: chunks
            chunk_texts = self.chunk_text(input_data.full_text)
            chunk_ids = self.create_chunks(
                doc_id=doc_id,
                chunk_texts=chunk_texts,
                topic=input_data.topic,
                content_type=input_data.content_type,
            )
            result.chunks_count = len(chunk_ids)

            # Шаг 4: embeddings
            embeddings = self.generate_embeddings(chunk_texts)
            count = self.store_embeddings(
                chunk_ids=chunk_ids,
                texts=chunk_texts,
                embeddings=embeddings,
                source_id=self.source_id,
                topic=input_data.topic,
            )
            result.embeddings_count = count

            logger.info(
                "Материал %s обработан: %d чанков, %d эмбеддингов",
                input_data.slug,
                result.chunks_count,
                result.embeddings_count,
            )

        except Exception as e:
            logger.exception("Ошибка обработки материала %s", input_data.slug)
            result.success = False
            result.error = str(e)

        return result

    # -------------------------------------------------------------------------
    # Пакетная обработка
    # -------------------------------------------------------------------------

    def process_batch(self, inputs: list[ContentInput]) -> PipelineBatchResult:
        """Выполняет пайплайн для списка материалов.

        Args:
            inputs: Список входных данных.

        Returns:
            Результат пакетной обработки PipelineBatchResult.
        """
        result = PipelineBatchResult(total=len(inputs))

        for input_data in inputs:
            item_result = self.process(input_data)
            result.results.append(item_result)

            if item_result.success:
                result.inserted += 1
            elif item_result.error == "duplicate":
                result.skipped += 1
            else:
                result.failed += 1

        logger.info(
            "Пакетная обработка завершена: всего %d, добавлено %d, пропущено %d, ошибок %d",
            result.total,
            result.inserted,
            result.skipped,
            result.failed,
        )

        return result


__all__ = [
    "ContentPipeline",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "COLLECTION_NAME",
    "CHUNK_SIZE_TARGET",
    "DEFAULT_SOURCE_TYPE",
]
