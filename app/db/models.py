# app/db/models.py
# --- agent_meta ---
# role: db-models
# contract: описывает pydantic-модели для таблиц пользователей, сессий и истории
# owner: backend-core
# --- /agent_meta ---

"""Pydantic-модели, отражающие структуру таблиц PostgreSQL."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """Карточка пользователя из таблицы users."""

    user_id: UUID
    external_id: str
    email: EmailStr
    profile_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """Модель для создания пользователя."""

    external_id: str = Field(..., min_length=1)
    email: EmailStr
    profile_json: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """Модель сессии из таблицы sessions."""

    session_id: UUID
    user_id: UUID
    mode: str
    status: str
    state_json: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None


class SessionCreate(BaseModel):
    """Входные данные для создания сессии."""

    user_id: UUID
    mode: str
    status: str = "active"
    state_json: dict[str, Any] = Field(default_factory=dict)


class SessionUpdateStatus(BaseModel):
    """Модель для обновления статуса сессии."""

    session_id: UUID
    status: str
    state_json: dict[str, Any] | None = None


class ChatMessage(BaseModel):
    """Сообщение из chat_history."""

    message_id: UUID
    session_id: UUID
    user_id: UUID
    sender: Literal["user", "assistant"]
    message_type: str
    payload: dict[str, Any]
    request_timestamp: datetime
    response_timestamp: datetime | None
    conversion_completed: bool
    expert_score: int | None
    user_score: int | None


class ChatMessageCreate(BaseModel):
    """Входные данные для записи сообщения."""

    session_id: UUID
    user_id: UUID
    sender: Literal["user", "assistant"]
    message_type: str
    payload: dict[str, Any]
    request_timestamp: datetime | None = None
    response_timestamp: datetime | None = None
    conversion_completed: bool = False
    expert_score: int | None = Field(default=None, ge=1, le=5)
    user_score: int | None = Field(default=None, ge=1, le=5)


class QuizAnswer(BaseModel):
    """Ответ на конкретный вопрос квиза."""

    value: Any
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    updated_at: datetime


class QuizAnswerUpdate(BaseModel):
    """Данные для обновления ответа."""

    value: Any
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    updated_at: datetime | None = None


class QuizProfile(BaseModel):
    """Снимок квиз-профиля пользователя."""

    version: str | None = None
    completed: bool = False
    completed_at: datetime | None = None
    answers: dict[str, QuizAnswer] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class QuizProfileUpdate(BaseModel):
    """Частичное обновление квиз-профиля."""

    version: str | None = None
    completed: bool | None = None
    completed_at: datetime | None = None
    answers: dict[str, QuizAnswerUpdate] = Field(default_factory=dict)
    meta: dict[str, Any] | None = None


class UserMemory(BaseModel):
    """Структура долговременной памяти пользователя."""

    memory_id: UUID
    user_id: UUID
    memory_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UserMemoryUpsert(BaseModel):
    """Данные для создания или обновления памяти."""

    user_id: UUID
    memory_data: dict[str, Any]


if __name__ == "__main__":
    example = UserCreate(external_id="demo-user", email="demo@example.com")
    print("Пример модели UserCreate:", example.model_dump())
