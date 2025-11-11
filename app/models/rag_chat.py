# app/models/rag_chat.py
# --- agent_meta ---
# role: rag-chat-models
# contract: схемы ответа и источников для контентного RAG-агента
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - RagReference
#   - RagReply
# --- /agent_meta ---

"""Pydantic-модели для RAG-агента по материалам психолога."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RagReference(BaseModel):
    """Описание куска контента, на который агент опирается в ответе."""

    chunk_id: str = Field(..., description="Идентификатор чанка в content_chunks.")
    doc_id: str = Field(..., description="Документ, из которого взят чанк.")
    preview: str = Field(..., description="Краткая цитата или выжимка.")
    topic: str | None = Field(default=None, description="Основная тема, если определена.")


class RagReply(BaseModel):
    """Структурированный ответ RAG-агента."""

    tone: Literal["gentle", "coach", "direct"] = Field(
        default="gentle",
        description="Выбранный тон общения агента.",
    )
    message: str = Field(..., description="Основной ответ пользователю с контекстом.")
    references: list[RagReference] = Field(
        default_factory=list,
        description="Материалы, на которые агент ссылался.",
    )
    follow_up_question: str = Field(
        ...,
        description="Вопрос для продолжения диалога.",
    )
