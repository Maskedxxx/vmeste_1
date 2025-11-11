# app/models/dialog_summary.py
# --- agent_meta ---
# role: dialog-summary-model
# contract: описывает структуру саммари диалога для хранения в user_memory
# owner: backend-core
# --- /agent_meta ---

"""Pydantic-схема структурированного саммари диалога."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DialogSummary(BaseModel):
    """Описание важной информации по диалогу."""

    emotional_state: str = Field(
        description="Как пользователь себя чувствует (тоновый вывод).",
    )
    key_events: list[str] = Field(
        default_factory=list,
        description="Основные факты и события, которые обсуждались.",
    )
    user_goals: list[str] = Field(
        default_factory=list,
        description="Какие цели или запросы озвучил пользователь.",
    )
    blockers: list[str] = Field(
        default_factory=list,
        description="Что мешает пользователю двигаться дальше.",
    )
    assistant_actions: list[str] = Field(
        default_factory=list,
        description="Какие шаги предложил ассистент или какие действия запланированы.",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Что важно сделать перед следующей встречей.",
    )
    concise_summary: str = Field(
        description="Сжатый абзац, объединяющий ключевые выводы разговора.",
    )

