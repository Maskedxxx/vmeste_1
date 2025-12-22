# tests/test_database.py
"""
Integration тесты для проверки работы с реальной PostgreSQL.

Эти тесты требуют запущенной тестовой БД:
    docker compose -f docker-compose.test.yml up -d

Все тесты используют фикстуру clean_tables которая автоматически очищает таблицы.
"""

import pytest
from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.db.models import (
    ChatMessageCreate,
    SessionCreate,
    UserCreate,
    UserMemoryUpsert,
)
from app.db.repositories import chat_history, sessions, user_memory, users


# =============================================================================
# Тесты репозитория users
# =============================================================================

@pytest.mark.integration
def test_create_user(clean_tables, db_connection: Connection):
    """
    Проверяет что create_user() успешно создаёт пользователя в БД.

    После создания пользователь должен быть доступен через get_by_email().
    """
    # Создаём пользователя
    user_data = UserCreate(
        external_id="test-001",
        email="user001@example.com",
        profile_json={"age": 30}
    )
    created_user = users.create_user(user_data)

    # Проверки
    assert created_user.user_id is not None
    assert created_user.external_id == "test-001"
    assert created_user.email == "user001@example.com"
    assert created_user.profile_json == {"age": 30}
    assert created_user.created_at is not None

    # Проверяем что пользователь есть в БД
    found_user = users.get_by_email("user001@example.com")
    assert found_user is not None
    assert found_user.user_id == created_user.user_id


@pytest.mark.integration
def test_email_unique_constraint(clean_tables, db_connection: Connection):
    """
    Проверяет что UNIQUE constraint на email работает.

    Попытка создать второго пользователя с тем же email должна вызвать ошибку.
    """
    # Создаём первого пользователя
    user1 = UserCreate(
        external_id="test-002",
        email="duplicate@example.com",
        profile_json={}
    )
    users.create_user(user1)

    # Попытка создать второго с тем же email должна упасть
    user2 = UserCreate(
        external_id="test-003",  # Другой external_id
        email="duplicate@example.com",  # Тот же email
        profile_json={}
    )

    with pytest.raises(Exception) as exc_info:
        users.create_user(user2)

    # Проверяем что это ошибка уникальности
    # psycopg выбрасывает либо UniqueViolation либо обёрнутую ошибку
    error_msg = str(exc_info.value).lower()
    assert "unique" in error_msg or "duplicate" in error_msg


# =============================================================================
# Тесты репозитория user_memory
# =============================================================================

@pytest.mark.integration
def test_upsert_memory(db_connection: Connection):
    """
    Проверяет что upsert_memory() создаёт новую запись и обновляет существующую.

    Используется механизм INSERT ON CONFLICT для идемпотентности.
    """
    # Создаём пользователя
    user = users.create_user(UserCreate(
        external_id="test-004",
        email="memory@example.com"
    ))

    # Первый вызов — создание
    memory1 = user_memory.upsert_memory(UserMemoryUpsert(
        user_id=user.user_id,
        memory_data={"key": "value1"}
    ))
    assert memory1.memory_id is not None
    assert memory1.memory_data == {"key": "value1"}

    # Второй вызов — обновление (тот же user_id)
    memory2 = user_memory.upsert_memory(UserMemoryUpsert(
        user_id=user.user_id,
        memory_data={"key": "value2", "new_key": "new_value"}
    ))

    # memory_id должен остаться тем же (UPDATE, не INSERT)
    assert memory2.memory_id == memory1.memory_id
    assert memory2.memory_data == {"key": "value2", "new_key": "new_value"}
    assert memory2.updated_at > memory1.updated_at


@pytest.mark.integration
def test_append_conversation_entry(db_connection: Connection):
    """
    Проверяет что append_conversation_entry() добавляет сообщения в массив JSONB.

    Каждое новое сообщение должно добавляться в conversation_history.
    """
    # Создаём пользователя
    user = users.create_user(UserCreate(
        external_id="test-005",
        email="conversation@example.com"
    ))

    # Добавляем первое сообщение
    user_memory.append_conversation_entry(
        user_id=user.user_id,
        entry={
            "role": "user",
            "payload": {"text": "Привет"},
            "message_type": "text"
        }
    )

    # Добавляем второе сообщение
    user_memory.append_conversation_entry(
        user_id=user.user_id,
        entry={
            "role": "assistant",
            "payload": {"text": "Привет! Как дела?"},
            "message_type": "text"
        }
    )

    # Проверяем что оба сообщения в памяти
    memory = user_memory.get_memory(user.user_id)
    assert memory is not None
    history = memory.memory_data.get("conversation_history", [])
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["payload"]["text"] == "Привет"
    assert history[1]["role"] == "assistant"
    assert history[1]["payload"]["text"] == "Привет! Как дела?"


# =============================================================================
# Тесты репозитория chat_history
# =============================================================================

@pytest.mark.integration
def test_add_message_with_fk(db_connection: Connection):
    """
    Проверяет что add_message() корректно работает с FK на sessions и users.

    Сообщение должно быть привязано к существующей сессии и пользователю.
    """
    # Создаём пользователя
    user = users.create_user(UserCreate(
        external_id="test-006",
        email="chat@example.com"
    ))

    # Создаём сессию
    session = sessions.create_session(SessionCreate(
        user_id=user.user_id,
        mode="intake",
        status="active"
    ))

    # Добавляем сообщение
    message = chat_history.add_message(ChatMessageCreate(
        session_id=session.session_id,
        user_id=user.user_id,
        sender="user",
        message_type="text",
        payload={"text": "Тестовое сообщение"}
    ))

    # Проверки
    assert message.message_id is not None
    assert message.session_id == session.session_id
    assert message.user_id == user.user_id
    assert message.sender == "user"
    assert message.payload == {"text": "Тестовое сообщение"}

    # Проверяем что сообщение можно достать через list_by_session
    messages = chat_history.list_by_session(session.session_id)
    assert len(messages) == 1
    assert messages[0].message_id == message.message_id
