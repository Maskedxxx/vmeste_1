# app/db/repositories/user_memory.py
# --- agent_meta ---
# role: user-memory-repository
# contract: чтение и обновление долговременной памяти пользователя
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий для работы с user_memory."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, MutableMapping
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_one
from app.db.models import UserMemory, UserMemoryUpsert


logger = logging.getLogger("vmeste.db.repositories.user_memory")

MEMORY_COLUMNS = (
    "memory_id",
    "user_id",
    "memory_data",
    "created_at",
    "updated_at",
)


def get_memory(user_id: UUID) -> UserMemory | None:
    """Возвращает память пользователя или None."""
    logger.debug("Чтение памяти user_id=%s", user_id)
    query = f"""
        SELECT {", ".join(MEMORY_COLUMNS)}
        FROM user_memory
        WHERE user_id = %(user_id)s
    """
    row = fetch_one(query, {"user_id": user_id})
    return UserMemory.model_validate(row) if row else None


def upsert_memory(payload: UserMemoryUpsert) -> UserMemory:
    """Создаёт или обновляет память пользователя."""
    logger.info("Обновление памяти user_id=%s", payload.user_id)
    query = f"""
        INSERT INTO user_memory (user_id, memory_data)
        VALUES (%(user_id)s, %(memory_data)s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            memory_data = EXCLUDED.memory_data,
            updated_at = NOW()
        RETURNING {", ".join(MEMORY_COLUMNS)}
    """
    row = fetch_one(
        query,
        {
            "user_id": payload.user_id,
            "memory_data": Json(payload.memory_data),
        },
    )
    if row is None:
        msg = "Не удалось обновить память пользователя"
        logger.error(msg)
        raise RuntimeError(msg)
    return UserMemory.model_validate(row)


__all__ = [
    "get_memory",
    "upsert_memory",
    "append_conversation_entry",
]


def _ensure_memory_structure(memory_data: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Гарантирует наличие базовых ключей в памяти."""
    if "conversation_history" not in memory_data:
        memory_data["conversation_history"] = []
    return memory_data


def append_conversation_entry(
    user_id: UUID,
    entry: dict[str, Any],
    max_length: int = 2000,
) -> UserMemory:
    """Добавляет сообщение в conversation_history с ограничением длины."""
    logger.debug("Добавление записи в память user_id=%s", user_id)
    memory = get_memory(user_id)
    memory_data: MutableMapping[str, Any]
    if memory:
        memory_data = dict(memory.memory_data)
    else:
        memory_data = {}
    memory_data = _ensure_memory_structure(memory_data)

    history: list[dict[str, Any]] = list(memory_data["conversation_history"])

    timestamp = entry.get("timestamp")
    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc).isoformat()
    else:
        if isinstance(timestamp, datetime):
            timestamp = timestamp.astimezone(timezone.utc).isoformat()
        else:
            timestamp = str(timestamp)
    entry["timestamp"] = timestamp
    history.append(entry)
    if len(history) > max_length:
        history = history[-max_length:]
    memory_data["conversation_history"] = history

    return upsert_memory(
        UserMemoryUpsert(
            user_id=user_id,
            memory_data=dict(memory_data),
        )
    )


if __name__ == "__main__":
    from uuid import uuid4
    from app.db.repositories.users import create_user, UserCreate

    demo_user = create_user(
        UserCreate(external_id=f"memory-demo-{uuid4()}", email="memory@example.com")
    )
    memory = upsert_memory(
        UserMemoryUpsert(
            user_id=demo_user.user_id,
            memory_data={"stress_level": "high"},
        )
    )
    print("Память обновлена:", memory.memory_id)
