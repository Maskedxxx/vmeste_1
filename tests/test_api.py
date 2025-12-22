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


# =============================================================================
# Тесты служебных эндпоинтов
# =============================================================================

@pytest.mark.api
def test_health_check(client: TestClient):
    """
    Проверяет что GET /health возвращает статус сервиса.

    Этот endpoint используется для health checks в production.
    """
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"


# =============================================================================
# Тесты эндпоинтов работы с пользователями
# =============================================================================

@pytest.mark.api
def test_get_user_by_email(
    client: TestClient,
    sample_user: dict[str, Any]
):
    """
    Проверяет что GET /users/email/{email} находит пользователя по email.

    Также проверяет 404 для несуществующего email.
    """
    email = sample_user["email"]
    user_id = sample_user["user_id"]

    # Запрашиваем существующего пользователя
    response = client.get(f"/users/email/{email}")
    assert response.status_code == 200

    user = response.json()
    assert user["user_id"] == user_id
    assert user["email"] == email

    # Запрашиваем несуществующего пользователя
    response_404 = client.get("/users/email/nonexistent@example.com")
    assert response_404.status_code == 404


@pytest.mark.api
def test_get_user_by_id(
    client: TestClient,
    sample_user: dict[str, Any]
):
    """
    Проверяет что GET /users/{user_id} находит пользователя по UUID.

    Также проверяет 404 для несуществующего UUID.
    """
    user_id = sample_user["user_id"]
    email = sample_user["email"]

    # Запрашиваем существующего пользователя
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200

    user = response.json()
    assert user["user_id"] == user_id
    assert user["email"] == email

    # Запрашиваем несуществующего пользователя
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response_404 = client.get(f"/users/{fake_uuid}")
    assert response_404.status_code == 404


@pytest.mark.api
def test_update_user_profile(
    client: TestClient,
    sample_user: dict[str, Any]
):
    """
    Проверяет что PUT /users/{user_id}/profile обновляет profile_json.

    Также проверяет 404 для несуществующего пользователя.
    """
    user_id = sample_user["user_id"]

    # Обновляем профиль
    new_profile = {"age": 25, "city": "Moscow", "interests": ["psychology"]}
    response = client.put(
        f"/users/{user_id}/profile",
        json={"profile_json": new_profile}
    )
    assert response.status_code == 200

    updated_user = response.json()
    assert updated_user["profile_json"] == new_profile

    # Проверяем что изменения сохранились
    get_response = client.get(f"/users/{user_id}")
    user = get_response.json()
    assert user["profile_json"] == new_profile

    # Проверяем 404 для несуществующего пользователя
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response_404 = client.put(
        f"/users/{fake_uuid}/profile",
        json={"profile_json": {"test": True}}
    )
    assert response_404.status_code == 404


# =============================================================================
# Тесты эндпоинтов управления сессиями
# =============================================================================

@pytest.mark.api
def test_get_active_session(
    client: TestClient,
    sample_user: dict[str, Any],
    sample_session: dict[str, Any]
):
    """
    Проверяет что GET /sessions/{user_id}/active возвращает активную сессию.

    Также проверяет что для пользователя без сессий возвращается null.
    """
    user_id = sample_user["user_id"]
    session_id = sample_session["session_id"]

    # Получаем активную сессию
    response = client.get(f"/sessions/{user_id}/active")
    assert response.status_code == 200

    session = response.json()
    assert session is not None
    assert session["session_id"] == session_id
    assert session["status"] == "active"

    # Создаём второго пользователя без сессий
    from uuid import uuid4
    user2_response = client.post(
        "/users",
        json={
            "external_id": f"no-sessions-{uuid4()}",
            "email": f"no-sessions-{uuid4()}@example.com"
        }
    )
    user2_id = user2_response.json()["user_id"]

    # Проверяем что для пользователя без сессий возвращается null
    response_none = client.get(f"/sessions/{user2_id}/active")
    assert response_none.status_code == 200
    assert response_none.json() is None


@pytest.mark.api
def test_close_session(
    client: TestClient,
    sample_session: dict[str, Any]
):
    """
    Проверяет что POST /sessions/{session_id}/close завершает сессию.

    Также проверяет 404 для несуществующей сессии.
    """
    session_id = sample_session["session_id"]

    # Закрываем сессию
    response = client.post(
        f"/sessions/{session_id}/close",
        json={"status": "completed"}
    )
    assert response.status_code == 200

    closed_session = response.json()
    assert closed_session["status"] == "completed"
    assert closed_session["ended_at"] is not None

    # Проверяем 404 для несуществующей сессии
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response_404 = client.post(
        f"/sessions/{fake_uuid}/close",
        json={"status": "completed"}
    )
    assert response_404.status_code == 404


@pytest.mark.api
def test_update_session_state(
    client: TestClient,
    sample_session: dict[str, Any]
):
    """
    Проверяет что PATCH /sessions/{session_id}/state обновляет state_json.

    Также проверяет 404 для несуществующей сессии.
    """
    session_id = sample_session["session_id"]

    # Обновляем состояние сессии
    new_state = {"step": "intake_done", "next_action": "consultation"}
    response = client.patch(
        f"/sessions/{session_id}/state",
        json={"state_json": new_state}
    )
    assert response.status_code == 200

    updated_session = response.json()
    assert updated_session["state_json"] == new_state

    # Проверяем 404 для несуществующей сессии
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response_404 = client.patch(
        f"/sessions/{fake_uuid}/state",
        json={"state_json": {"test": True}}
    )
    assert response_404.status_code == 404


# =============================================================================
# Тесты эндпоинтов истории сообщений
# =============================================================================

@pytest.mark.api
def test_get_user_messages(
    client: TestClient,
    sample_user: dict[str, Any]
):
    """
    Проверяет что GET /users/{user_id}/messages возвращает все сообщения пользователя.

    Проверяет работу параметра limit.
    """
    user_id = sample_user["user_id"]

    # Создаём 2 сессии
    session1 = client.post(
        "/sessions",
        json={"user_id": user_id, "mode": "intake", "status": "active"}
    ).json()
    session2 = client.post(
        "/sessions",
        json={"user_id": user_id, "mode": "consultation", "status": "active"}
    ).json()

    # Добавляем по 2 сообщения в каждую сессию (всего 4)
    for session_id in [session1["session_id"], session2["session_id"]]:
        for i in range(1, 3):
            client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "user_id": user_id,
                    "sender": "user",
                    "message_type": "text",
                    "payload": {"text": f"Message {i} in session {session_id}"}
                }
            )

    # Получаем все сообщения пользователя
    response = client.get(f"/users/{user_id}/messages")
    assert response.status_code == 200

    messages = response.json()
    assert len(messages) == 4

    # Проверяем лимит
    response_limited = client.get(f"/users/{user_id}/messages?limit=2")
    assert response_limited.status_code == 200

    limited_messages = response_limited.json()
    assert len(limited_messages) == 2
