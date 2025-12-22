# app/db/repositories/sessions.py
# --- agent_meta ---
# role: sessions-repository
# contract: управление жизненным циклом сессий пользователей
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий для таблицы sessions."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_one
from app.db.models import Session, SessionCreate


logger = logging.getLogger("vmeste.db.repositories.sessions")

SESSION_COLUMNS = (
    "session_id",
    "user_id",
    "mode",
    "status",
    "state_json",
    "started_at",
    "ended_at",
)


def create_session(payload: SessionCreate) -> Session:
    """Создаёт новую сессию для пользователя."""
    logger.info("Создание сессии user_id=%s mode=%s", payload.user_id, payload.mode)
    query = f"""
        INSERT INTO sessions (user_id, mode, status, state_json)
        VALUES (%(user_id)s, %(mode)s, %(status)s, %(state_json)s)
        RETURNING {", ".join(SESSION_COLUMNS)}
    """
    params = {
        "user_id": payload.user_id,
        "mode": payload.mode,
        "status": payload.status,
        "state_json": Json(payload.state_json),
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать сессию"
        logger.error(msg)
        raise RuntimeError(msg)
    return Session.model_validate(row)


def get_active_session(user_id: UUID) -> Session | None:
    """Возвращает активную сессию пользователя (status=active)."""
    logger.debug("Поиск активной сессии user_id=%s", user_id)
    query = f"""
        SELECT {", ".join(SESSION_COLUMNS)}
        FROM sessions
        WHERE user_id = %(user_id)s
          AND status = 'active'
        ORDER BY started_at DESC
        LIMIT 1
    """
    row = fetch_one(query, {"user_id": user_id})
    return Session.model_validate(row) if row else None


def close_session(session_id: UUID, status: str, ended_at: datetime | None = None) -> Session:
    """Переводит сессию в завершающий статус и проставляет ended_at."""
    logger.info("Закрытие сессии %s, статус=%s", session_id, status)
    query = f"""
        UPDATE sessions
        SET status = %(status)s,
            ended_at = COALESCE(%(ended_at)s, NOW())
        WHERE session_id = %(session_id)s
        RETURNING {", ".join(SESSION_COLUMNS)}
    """
    row = fetch_one(
        query,
        {
            "session_id": session_id,
            "status": status,
            "ended_at": ended_at,
        },
    )
    if row is None:
        msg = f"Сессия {session_id} не найдена"
        logger.error(msg)
        raise LookupError(msg)
    return Session.model_validate(row)


def update_state(session_id: UUID, state_json: dict) -> Session:
    """Обновляет состояние графа в рамках активной сессии."""
    logger.debug("Обновление state_json session_id=%s", session_id)
    query = f"""
        UPDATE sessions
        SET state_json = %(state_json)s
        WHERE session_id = %(session_id)s
        RETURNING {", ".join(SESSION_COLUMNS)}
    """
    row = fetch_one(
        query,
        {
            "session_id": session_id,
            "state_json": Json(state_json),
        },
    )
    if row is None:
        msg = f"Сессия {session_id} не найдена"
        logger.error(msg)
        raise LookupError(msg)
    return Session.model_validate(row)


__all__ = [
    "create_session",
    "get_active_session",
    "close_session",
    "update_state",
]


if __name__ == "__main__":
    from uuid import uuid4
    from app.db.repositories.users import create_user, UserCreate

    demo_user = create_user(UserCreate(external_id=f"session-demo-{uuid4()}"))
    demo_session = create_session(
        SessionCreate(
            user_id=demo_user.user_id,
            mode="intake",
            status="active",
        )
    )
    print("Создана сессия:", demo_session.session_id)
