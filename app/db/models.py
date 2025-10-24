# app/db/models.py
# --- agent_meta ---
# role: db-models
# contract: описывает pydantic-модели для таблиц пользователей и сессий
# owner: backend-core
# --- /agent_meta ---

"""Pydantic-модели, отражающие структуру таблиц PostgreSQL."""

from datetime import datetime
from typing import Any
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
    status: str
    state_json: dict[str, Any] = Field(default_factory=dict)


class SessionUpdateStatus(BaseModel):
    """Модель для обновления статуса сессии."""

    session_id: UUID
    status: str
    state_json: dict[str, Any] | None = None


if __name__ == "__main__":
    example = UserCreate(external_id="demo-user")
    print("Пример модели UserCreate:", example.model_dump())
