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

from pydantic import BaseModel, Field


class User(BaseModel):
    """Карточка пользователя из таблицы users."""

    user_id: UUID
    external_id: str
    profile_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    """Модель для создания пользователя."""

    external_id: str = Field(..., min_length=1)
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
    expert_score: int | None = None
    user_score: int | None = None


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
    example = UserCreate(external_id="demo-user")
    print("Пример модели UserCreate:", example.model_dump())
