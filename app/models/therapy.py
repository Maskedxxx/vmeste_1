# app/models/therapy.py
# --- agent_meta ---
# role: therapy-agent-models
# contract: описывает структуру ответа терапевтического агента
# owner: backend-core
# --- /agent_meta ---

"""Pydantic-схема ответа терапевтического агента."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TherapyReply(BaseModel):
    """Структурированный ответ агента поддержки."""

    style: Literal["gentle", "grounded", "coaching"] = Field(
        default="gentle",
        description="Какой тон выбрал агент в этом ответе.",
    )
    message: str = Field(
        ...,
        description="Основной эмпатичный ответ для пользователя.",
    )
    coping_tips: list[str] = Field(
        default_factory=list,
        description="Короткие практические советы или техники самопомощи.",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="1-2 вопроса, чтобы продолжить разговор и углубить понимание.",
    )
    next_step: str = Field(
        ...,
        description="Что агент предлагает сделать дальше (например, поделиться наблюдением, попробовать упражнение).",
    )
