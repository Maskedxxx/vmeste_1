# tests/test_core.py
"""
Unit тесты для критичной бизнес-логики.

Эти тесты изолированы от БД и используют моки для быстрого выполнения.
"""

import pytest
from pydantic import ValidationError

from app.db.models import ChatMessageCreate, QuizAnswer, UserCreate
from app.db.repositories.user_memory import _ensure_memory_structure, _merge_quiz_profile


# =============================================================================
# Тесты валидации Pydantic моделей
# =============================================================================

@pytest.mark.unit
def test_email_validation():
    """
    Проверяет что EmailStr корректно валидирует email адреса.

    Валидные email должны проходить, невалидные — выбрасывать ValidationError.
    """
    # Валидные email должны проходить
    valid_user = UserCreate(
        external_id="test-123",
        email="valid@example.com",
        profile_json={}
    )
    assert valid_user.email == "valid@example.com"

    # Невалидные email должны выбрасывать ошибку
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(
            external_id="test-456",
            email="invalid-email",  # Нет @
            profile_json={}
        )
    # Проверяем что ошибка связана с полем email
    assert "email" in str(exc_info.value)


@pytest.mark.unit
def test_score_constraints():
    """
    Проверяет что expert_score и user_score принимают только значения 1-5 или None.

    Значения вне диапазона должны выбрасывать ValidationError.
    """
    # Валидные scores (1-5)
    for score in [1, 2, 3, 4, 5]:
        message = ChatMessageCreate(
            session_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000002",
            sender="user",
            message_type="text",
            payload={"text": "test"},
            expert_score=score,
            user_score=score
        )
        assert message.expert_score == score
        assert message.user_score == score

    # None тоже валиден
    message_none = ChatMessageCreate(
        session_id="00000000-0000-0000-0000-000000000001",
        user_id="00000000-0000-0000-0000-000000000002",
        sender="user",
        message_type="text",
        payload={"text": "test"},
        expert_score=None,
        user_score=None
    )
    assert message_none.expert_score is None
    assert message_none.user_score is None

    # Значения вне диапазона должны ошибку выбрасывать
    with pytest.raises(ValidationError):
        ChatMessageCreate(
            session_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000002",
            sender="user",
            message_type="text",
            payload={"text": "test"},
            expert_score=0  # Слишком мало
        )

    with pytest.raises(ValidationError):
        ChatMessageCreate(
            session_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000002",
            sender="user",
            message_type="text",
            payload={"text": "test"},
            user_score=6  # Слишком много
        )


# =============================================================================
# Тесты бизнес-логики user_memory
# =============================================================================

@pytest.mark.unit
def test_merge_quiz_profile():
    """
    Проверяет что _merge_quiz_profile() корректно объединяет существующие и новые ответы.

    Новые ответы должны добавляться, существующие — обновляться.
    """
    from datetime import datetime, timezone
    from app.db.models import QuizProfile, QuizProfileUpdate, QuizAnswerUpdate

    now = datetime.now(timezone.utc)

    # Существующий профиль с одним ответом
    existing = QuizProfile(
        version="1.0",
        completed=False,
        answers={
            "family_structure": QuizAnswer(
                value="2 взрослых, 1 ребёнок",
                confidence=0.9,
                updated_at=now
            )
        }
    )

    # Новые данные — добавляем второй ответ и обновляем первый
    update = QuizProfileUpdate(
        answers={
            "family_structure": QuizAnswerUpdate(
                value="2 взрослых, 2 детей",  # Обновляем
                confidence=1.0,
                updated_at=now
            ),
            "primary_concern": QuizAnswerUpdate(
                value="Стресс на работе",  # Добавляем новый
                confidence=0.8,
                updated_at=now
            )
        },
        completed=True
    )

    # Выполняем мердж
    merged = _merge_quiz_profile(existing, update)

    # Проверки
    assert merged.completed is True  # Обновился флаг
    assert len(merged.answers) == 2  # Теперь 2 ответа
    assert merged.answers["family_structure"].value == "2 взрослых, 2 детей"  # Обновлён
    assert merged.answers["family_structure"].confidence == 1.0
    assert merged.answers["primary_concern"].value == "Стресс на работе"  # Добавлен


@pytest.mark.unit
def test_conversation_history_limit():
    """
    Проверяет что история обрезается до max_length=2000 сообщений.

    Если в истории больше 2000 записей, должны сохраниться только последние 2000.
    """
    from app.db.repositories.user_memory import append_conversation_entry
    from unittest.mock import MagicMock, patch

    # Создаём память с 2005 сообщениями
    memory_data = {
        "conversation_history": [
            {"role": "user", "payload": {"text": f"Message {i}"}, "timestamp": f"2025-01-{i:02d}"}
            for i in range(1, 2006)  # 2005 сообщений
        ]
    }

    # Мокаем get_memory чтобы вернуть нашу память
    mock_memory = MagicMock()
    mock_memory.memory_data = memory_data

    with patch("app.db.repositories.user_memory.get_memory", return_value=mock_memory):
        with patch("app.db.repositories.user_memory.upsert_memory") as mock_upsert:
            # Добавляем 2006-е сообщение
            append_conversation_entry(
                user_id="00000000-0000-0000-0000-000000000001",
                entry={"role": "user", "payload": {"text": "Message 2006"}},
                max_length=2000
            )

            # Проверяем что upsert_memory был вызван
            mock_upsert.assert_called_once()

            # Достаём аргументы вызова
            call_args = mock_upsert.call_args[0][0]
            saved_history = call_args.memory_data["conversation_history"]

            # История должна быть обрезана до 2000
            assert len(saved_history) == 2000
            # Первое сообщение должно быть #7 (6 удалилось)
            assert saved_history[0]["payload"]["text"] == "Message 7"
            # Последнее — #2006
            assert saved_history[-1]["payload"]["text"] == "Message 2006"


@pytest.mark.unit
def test_ensure_memory_structure():
    """
    Проверяет что _ensure_memory_structure() создаёт conversation_history если его нет.

    Функция должна гарантировать наличие базовых ключей в memory_data.
    """
    # Пустая память
    empty_memory = {}
    result = _ensure_memory_structure(empty_memory)

    assert "conversation_history" in result
    assert isinstance(result["conversation_history"], list)
    assert len(result["conversation_history"]) == 0

    # Память с другими ключами — не должны пропасть
    memory_with_keys = {"quiz_profile": {"version": "1.0"}}
    result = _ensure_memory_structure(memory_with_keys)

    assert "conversation_history" in result
    assert "quiz_profile" in result  # Старый ключ сохранён
    assert result["quiz_profile"]["version"] == "1.0"
