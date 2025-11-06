"""Точка входа FastAPI-приложения для проекта «Вместе» (v0)."""

from datetime import datetime, timezone
import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.db.models import (
    ChatMessage,
    ChatMessageCreate,
    QuizProfile,
    QuizProfileUpdate,
    Session,
    SessionCreate,
    User,
    UserCreate,
    UserMemory,
    UserMemoryUpsert,
)
from app.db.repositories import chat_history, sessions, user_memory, users


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vmeste.api")

app = FastAPI(title="Vmeste API", version="0.3.0")


class HealthResponse(BaseModel):
    """Ответ сервиса на проверку работоспособности."""

    status: Literal["ok"]


class CloseSessionRequest(BaseModel):
    """Параметры закрытия сессии."""

    status: str = Field(..., min_length=1)
    ended_at: datetime | None = None


class UpdateStateRequest(BaseModel):
    """Новый стейт для сессии."""

    state_json: dict[str, object] = Field(default_factory=dict)


class ChatMessageRequest(BaseModel):
    """Запрос на добавление сообщения в сессию."""

    user_id: UUID
    sender: Literal["user", "assistant"]
    message_type: str = "text"
    payload: dict[str, object]
    request_timestamp: datetime | None = None
    response_timestamp: datetime | None = None
    conversion_completed: bool = False
    expert_score: int | None = Field(default=None, ge=1, le=5)
    user_score: int | None = Field(default=None, ge=1, le=5)


class MemoryRequest(BaseModel):
    """Запрос на обновление памяти пользователя."""

    memory_data: dict[str, object]


class ProfileRequest(BaseModel):
    """Запрос на обновление профиля пользователя."""

    profile_json: dict[str, object]


@app.get("/health", response_model=HealthResponse, tags=["service"])
def health_check() -> HealthResponse:
    """Возвращает статус сервиса."""
    logger.debug("Получен запрос /health")
    return HealthResponse(status="ok")


@app.post("/users", response_model=User, tags=["users"], status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> User:
    """Создаёт пользователя или возвращает существующего по email."""
    existing = users.get_by_email(payload.email)
    if existing:
        logger.info("Пользователь %s уже существует", payload.email)
        return existing
    return users.create_user(payload)


@app.get("/users/email/{email}", response_model=User, tags=["users"])
def get_user_by_email(email: EmailStr) -> User:
    """Возвращает пользователя по email."""
    user = users.get_by_email(str(email))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.get("/users/{user_id}", response_model=User, tags=["users"])
def get_user(user_id: UUID) -> User:
    """Возвращает пользователя по внутреннему идентификатору."""
    user = users.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.put("/users/{user_id}/profile", response_model=User, tags=["users"])
def update_profile(user_id: UUID, payload: ProfileRequest) -> User:
    """Обновляет профиль пользователя."""
    try:
        return users.update_profile(user_id, payload.profile_json)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.post("/sessions", response_model=Session, tags=["sessions"], status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate) -> Session:
    """Создаёт новую сессию."""
    return sessions.create_session(payload)


@app.get("/sessions/{user_id}/active", response_model=Session | None, tags=["sessions"])
def get_active_session(user_id: UUID) -> Session | None:
    """Возвращает активную сессию пользователя, если она есть."""
    return sessions.get_active_session(user_id)


@app.post("/sessions/{session_id}/close", response_model=Session, tags=["sessions"])
def close_session(session_id: UUID, payload: CloseSessionRequest) -> Session:
    """Закрывает сессию с указанным статусом."""
    try:
        return sessions.close_session(session_id, payload.status, payload.ended_at)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.patch("/sessions/{session_id}/state", response_model=Session, tags=["sessions"])
def update_session_state(session_id: UUID, payload: UpdateStateRequest) -> Session:
    """Обновляет state_json сессии."""
    try:
        return sessions.update_state(session_id, payload.state_json)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessage,
    tags=["chat"],
    status_code=status.HTTP_201_CREATED,
)
def add_message(session_id: UUID, payload: ChatMessageRequest) -> ChatMessage:
    """Сохраняет сообщение в истории чата и добавляет его в долговременную память."""
    message = ChatMessageCreate(
        session_id=session_id,
        user_id=payload.user_id,
        sender=payload.sender,
        message_type=payload.message_type,
        payload=payload.payload,
        request_timestamp=payload.request_timestamp,
        response_timestamp=payload.response_timestamp,
        conversion_completed=payload.conversion_completed,
        expert_score=payload.expert_score,
        user_score=payload.user_score,
    )
    stored = chat_history.add_message(message)

    timestamp = stored.response_timestamp or stored.request_timestamp or datetime.now(timezone.utc)
    history_entry = {
        "role": stored.sender,
        "message_type": stored.message_type,
        "payload": stored.payload,
        "timestamp": timestamp,
    }
    user_memory.append_conversation_entry(stored.user_id, history_entry)
    return stored


@app.get("/sessions/{session_id}/messages", response_model=list[ChatMessage], tags=["chat"])
def get_session_messages(session_id: UUID, limit: int = 100) -> list[ChatMessage]:
    """Возвращает сообщения указанной сессии."""
    return chat_history.list_by_session(session_id, limit=limit)


@app.get("/users/{user_id}/messages", response_model=list[ChatMessage], tags=["chat"])
def get_user_messages(user_id: UUID, limit: int = 200) -> list[ChatMessage]:
    """Возвращает сообщения пользователя через все сессии."""
    return chat_history.list_by_user(user_id, limit=limit)


@app.get("/users/{user_id}/memory", response_model=UserMemory | None, tags=["memory"])
def get_memory(user_id: UUID) -> UserMemory | None:
    """Возвращает память пользователя, если она есть."""
    return user_memory.get_memory(user_id)


@app.put("/users/{user_id}/memory", response_model=UserMemory, tags=["memory"])
def upsert_memory(user_id: UUID, payload: MemoryRequest) -> UserMemory:
    """Создаёт или обновляет память пользователя."""
    request = UserMemoryUpsert(user_id=user_id, memory_data=payload.memory_data)
    return user_memory.upsert_memory(request)


@app.get(
    "/users/{user_id}/quiz-profile",
    response_model=QuizProfile | None,
    tags=["memory"],
)
def get_quiz_profile(user_id: UUID) -> QuizProfile | None:
    """Возвращает результаты квиза, если они есть."""
    return user_memory.get_quiz_profile(user_id)


@app.put(
    "/users/{user_id}/quiz-profile",
    response_model=QuizProfile,
    tags=["memory"],
)
def update_quiz_profile(user_id: UUID, payload: QuizProfileUpdate) -> QuizProfile:
    """Обновляет квиз-профиль пользователя."""
    return user_memory.upsert_quiz_profile(user_id, payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
