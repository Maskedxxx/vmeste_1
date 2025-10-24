# app/db/repositories/chat_history.py
# --- agent_meta ---
# role: chat-history-repository
# contract: операции с таблицей chat_history
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий для таблицы chat_history."""

from __future__ import annotations

import logging
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_all, fetch_one
from app.db.models import ChatMessage, ChatMessageCreate


logger = logging.getLogger("vmeste.db.repositories.chat_history")

CHAT_COLUMNS = (
    "message_id",
    "session_id",
    "user_id",
    "sender",
    "message_type",
    "payload",
    "request_timestamp",
    "response_timestamp",
    "conversion_completed",
    "expert_score",
    "user_score",
)


def add_message(payload: ChatMessageCreate) -> ChatMessage:
    """Добавляет строку в chat_history."""
    logger.info(
        "Добавление сообщения session_id=%s sender=%s type=%s",
        payload.session_id,
        payload.sender,
        payload.message_type,
    )
    query = f"""
        INSERT INTO chat_history (
            session_id,
            user_id,
            sender,
            message_type,
            payload,
            request_timestamp,
            response_timestamp,
            conversion_completed,
            expert_score,
            user_score
        )
        VALUES (
            %(session_id)s,
            %(user_id)s,
            %(sender)s,
            %(message_type)s,
            %(payload)s,
            COALESCE(%(request_timestamp)s, NOW()),
            %(response_timestamp)s,
            %(conversion_completed)s,
            %(expert_score)s,
            %(user_score)s
        )
        RETURNING {", ".join(CHAT_COLUMNS)}
    """
    params = {
        "session_id": payload.session_id,
        "user_id": payload.user_id,
        "sender": payload.sender,
        "message_type": payload.message_type,
        "payload": Json(payload.payload),
        "request_timestamp": payload.request_timestamp,
        "response_timestamp": payload.response_timestamp,
        "conversion_completed": payload.conversion_completed,
        "expert_score": payload.expert_score,
        "user_score": payload.user_score,
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось записать сообщение"
        logger.error(msg)
        raise RuntimeError(msg)
    return ChatMessage.model_validate(row)


def list_by_session(session_id: UUID, limit: int = 100) -> list[ChatMessage]:
    """Возвращает сообщения указанной сессии."""
    logger.debug("Загрузка истории по session_id=%s", session_id)
    query = f"""
        SELECT {", ".join(CHAT_COLUMNS)}
        FROM chat_history
        WHERE session_id = %(session_id)s
        ORDER BY request_timestamp ASC
        LIMIT %(limit)s
    """
    rows = fetch_all(query, {"session_id": session_id, "limit": limit})
    return [ChatMessage.model_validate(row) for row in rows]


def list_by_user(user_id: UUID, limit: int = 200) -> list[ChatMessage]:
    """Возвращает сообщения пользователя через все сессии."""
    logger.debug("Загрузка истории по user_id=%s", user_id)
    query = f"""
        SELECT {", ".join(CHAT_COLUMNS)}
        FROM chat_history
        WHERE user_id = %(user_id)s
        ORDER BY request_timestamp DESC
        LIMIT %(limit)s
    """
    rows = fetch_all(query, {"user_id": user_id, "limit": limit})
    return [ChatMessage.model_validate(row) for row in rows]


__all__ = [
    "add_message",
    "list_by_session",
    "list_by_user",
]


if __name__ == "__main__":
    from uuid import uuid4
    from app.db.repositories.users import create_user, UserCreate
    from app.db.repositories.sessions import create_session, SessionCreate

    demo_user = create_user(UserCreate(external_id=f"chat-demo-{uuid4()}"))
    session = create_session(
        SessionCreate(
            user_id=demo_user.user_id,
            mode="intake",
            status="active",
        )
    )
    message = add_message(
        ChatMessageCreate(
            session_id=session.session_id,
            user_id=demo_user.user_id,
            sender="user",
            message_type="text",
            payload={"text": "Привет"},
        )
    )
    print("Добавлено сообщение:", message.message_id)
