# tests/test_api.py
"""
API тесты (E2E) для проверки всех эндпоинтов FastAPI.

Используют TestClient и реальную тестовую БД.
Запуск: docker compose -f docker-compose.test.yml up -d && pytest tests/test_api.py
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# Тесты эндпоинтов users
# =============================================================================

@pytest.mark.api
def test_create_user_idempotent(client: TestClient):
    """
    Проверяет идемпотентность POST /users.

    Два одинаковых запроса должны вернуть одного и того же пользователя.
    Второй запрос НЕ должен создавать дубликат.
    """
    user_data = {
        "external_id": "idempotent-test",
        "email": "idempotent@example.com",
        "profile_json": {"test": True}
    }

    # Первый запрос — создание
    response1 = client.post("/users", json=user_data)
    assert response1.status_code == 201
    user1 = response1.json()
    user1_id = user1["user_id"]

    # Второй запрос с тем же email — должен вернуть существующего
    response2 = client.post("/users", json=user_data)
    assert response2.status_code == 201  # Статус тот же
    user2 = response2.json()
    user2_id = user2["user_id"]

    # user_id должны совпадать (не создали дубликат)
    assert user1_id == user2_id
    assert user1["email"] == user2["email"]


# =============================================================================
# Тесты эндпоинтов chat и синхронизации с памятью
# =============================================================================

@pytest.mark.api
def test_post_message_dual_write(
    client: TestClient,
    sample_user: dict[str, Any],
    sample_session: dict[str, Any]
):
    """
    Проверяет что POST /sessions/{id}/messages записывает в ОБЕ таблицы.

    Сообщение должно попасть и в chat_history И в user_memory.conversation_history.
    """
    session_id = sample_session["session_id"]
    user_id = sample_user["user_id"]

    # Отправляем сообщение
    message_data = {
        "user_id": user_id,
        "sender": "user",
        "message_type": "text",
        "payload": {"text": "Проверка двойной записи"}
    }
    response = client.post(f"/sessions/{session_id}/messages", json=message_data)
    assert response.status_code == 201
    message = response.json()
    assert message["payload"]["text"] == "Проверка двойной записи"

    # Проверяем что сообщение в chat_history
    chat_response = client.get(f"/sessions/{session_id}/messages")
    assert chat_response.status_code == 200
    chat_messages = chat_response.json()
    assert len(chat_messages) >= 1
    assert any(msg["payload"]["text"] == "Проверка двойной записи" for msg in chat_messages)

    # Проверяем что сообщение в user_memory
    memory_response = client.get(f"/users/{user_id}/memory")
    assert memory_response.status_code == 200
    memory = memory_response.json()
    history = memory["memory_data"]["conversation_history"]
    assert len(history) >= 1
    assert any(msg["payload"]["text"] == "Проверка двойной записи" for msg in history)


@pytest.mark.api
def test_post_message_memory_sync(
    client: TestClient,
    sample_user: dict[str, Any],
    sample_session: dict[str, Any]
):
    """
    Проверяет что история в user_memory накапливается при добавлении сообщений.

    После отправки нескольких сообщений, все они должны быть в conversation_history.
    """
    session_id = sample_session["session_id"]
    user_id = sample_user["user_id"]

    # Отправляем 3 сообщения
    for i in range(1, 4):
        client.post(
            f"/sessions/{session_id}/messages",
            json={
                "user_id": user_id,
                "sender": "user",
                "message_type": "text",
                "payload": {"text": f"Сообщение {i}"}
            }
        )

    # Проверяем что все 3 в памяти
    memory_response = client.get(f"/users/{user_id}/memory")
    memory = memory_response.json()
    history = memory["memory_data"]["conversation_history"]

    assert len(history) == 3
    assert history[0]["payload"]["text"] == "Сообщение 1"
    assert history[1]["payload"]["text"] == "Сообщение 2"
    assert history[2]["payload"]["text"] == "Сообщение 3"


# =============================================================================
# Тесты эндпоинтов квиза
# =============================================================================

@pytest.mark.api
def test_quiz_profile_merge(
    client: TestClient,
    sample_user: dict[str, Any]
):
    """
    Проверяет что PUT /users/{id}/quiz-profile мерджит с существующим профилем.

    Первый запрос создаёт профиль, второй добавляет новые ответы не теряя старые.
    """
    user_id = sample_user["user_id"]

    # Первый запрос — создаём профиль с одним ответом
    quiz1 = {
        "answers": {
            "family_structure": {
                "value": "2 взрослых, 1 ребёнок",
                "confidence": 0.9
            }
        },
        "completed": False
    }
    response1 = client.put(f"/users/{user_id}/quiz-profile", json=quiz1)
    assert response1.status_code == 200

    # Второй запрос — добавляем второй ответ
    quiz2 = {
        "answers": {
            "primary_concern": {
                "value": "Стресс",
                "confidence": 0.8
            }
        },
        "completed": True
    }
    response2 = client.put(f"/users/{user_id}/quiz-profile", json=quiz2)
    assert response2.status_code == 200

    # Проверяем финальный профиль
    get_response = client.get(f"/users/{user_id}/quiz-profile")
    profile = get_response.json()

    # Оба ответа должны быть
    assert "family_structure" in profile["answers"]
    assert "primary_concern" in profile["answers"]
    assert profile["completed"] is True


# =============================================================================
# Тесты эндпоинтов памяти
# =============================================================================

@pytest.mark.api
def test_get_memory(
    client: TestClient,
    sample_user: dict[str, Any]
):
    """
    Проверяет что GET /users/{id}/memory возвращает валидный JSONB.

    Даже если память пустая, должна вернуться корректная структура.
    """
    user_id = sample_user["user_id"]

    # Сначала обновляем память
    memory_data = {
        "memory_data": {
            "custom_key": "custom_value",
            "conversation_history": []
        }
    }
    put_response = client.put(f"/users/{user_id}/memory", json=memory_data)
    assert put_response.status_code == 200

    # Теперь читаем
    get_response = client.get(f"/users/{user_id}/memory")
    assert get_response.status_code == 200

    memory = get_response.json()
    assert "memory_data" in memory
    assert memory["memory_data"]["custom_key"] == "custom_value"
    assert isinstance(memory["memory_data"]["conversation_history"], list)
