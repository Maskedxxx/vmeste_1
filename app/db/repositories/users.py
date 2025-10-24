# app/db/repositories/users.py
# --- agent_meta ---
# role: users-repository
# contract: CRUD-операции над таблицей users
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий пользователей."""

from typing import Any
import logging
from uuid import UUID

from psycopg.types.json import Json

from app.db.connection import fetch_one
from app.db.models import User, UserCreate


logger = logging.getLogger("vmeste.db.repositories.users")

USER_COLUMNS = (
    "user_id",
    "external_id",
    "email",
    "profile_json",
    "created_at",
    "updated_at",
)


def create_user(payload: UserCreate) -> User:
    """Создаёт пользователя и возвращает полную запись."""
    logger.info("Создание пользователя email=%s", payload.email)
    query = f"""
        INSERT INTO users (external_id, email, profile_json)
        VALUES (%(external_id)s, %(email)s, %(profile_json)s)
        RETURNING {", ".join(USER_COLUMNS)}
    """
    params = {
        "external_id": payload.external_id,
        "email": payload.email,
        "profile_json": Json(payload.profile_json),
    }
    row = fetch_one(query, params)
    if row is None:
        msg = "Не удалось создать пользователя"
        logger.error(msg)
        raise RuntimeError(msg)
    return User.model_validate(row)


def get_by_email(email: str) -> User | None:
    """Возвращает пользователя по email."""
    logger.debug("Поиск пользователя email=%s", email)
    query = f"""
        SELECT {", ".join(USER_COLUMNS)}
        FROM users
        WHERE email = %(email)s
    """
    row = fetch_one(query, {"email": email})
    return User.model_validate(row) if row else None


def get_by_id(user_id: UUID) -> User | None:
    """Возвращает пользователя по внутреннему идентификатору."""
    logger.debug("Поиск пользователя user_id=%s", user_id)
    query = f"""
        SELECT {", ".join(USER_COLUMNS)}
        FROM users
        WHERE user_id = %(user_id)s
    """
    row = fetch_one(query, {"user_id": user_id})
    return User.model_validate(row) if row else None


def update_profile(user_id: UUID, profile_json: dict[str, Any]) -> User:
    """Обновляет профиль пользователя."""
    logger.info("Обновление профиля user_id=%s", user_id)
    query = f"""
        UPDATE users
        SET profile_json = %(profile_json)s,
            updated_at = NOW()
        WHERE user_id = %(user_id)s
        RETURNING {", ".join(USER_COLUMNS)}
    """
    row = fetch_one(
        query,
        {
            "user_id": user_id,
            "profile_json": Json(profile_json),
        },
    )
    if row is None:
        msg = f"Пользователь {user_id} не найден"
        logger.error(msg)
        raise LookupError(msg)
    return User.model_validate(row)


__all__ = [
    "create_user",
    "get_by_email",
    "get_by_id",
    "update_profile",
]


if __name__ == "__main__":
    from uuid import uuid4

    demo = UserCreate(external_id=f"demo-{uuid4()}", email="demo@example.com")
    created_user = create_user(demo)
    print("Создан пользователь:", created_user.email)
