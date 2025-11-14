# app/services/profile_enrichment.py
# --- agent_meta ---
# role: profile-enrichment-service
# contract: вызывает LLM для генерации profile_json и сохраняет результат в БД
# owner: backend-core
# last_reviewed: 2025-11-10
# interfaces:
#   - ProfileEnrichmentService.generate_profile(...)
#   - enrich_user_profile(user_id: UUID, quiz_answers: Mapping[str, Any], extra_context: str | None)
# --- /agent_meta ---

"""Сервис для создания и дообогащения profile_json через LLM."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from openai import OpenAI

from app.db.repositories import user_memory, users
from app.models.user_profile import UserProfileModel
from config import get_settings


logger = logging.getLogger("vmeste.services.profile_enrichment")

SYSTEM_PROMPT = (
    "Ты аналитик психологической платформы «Вместе». "
    "На основе ответов квиза и дополнительного контекста сформируй структурированный "
    "профиль пользователя. Всегда возвращай JSON, который строго следует схеме. "
    "Если данных мало, аккуратно заполни известные поля и оставь остальные нейтральными."
)


class ProfileEnrichmentService:
    """Инкапсулирует работу с OpenAI Responses API."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model_name = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate_profile(
        self,
        *,
        quiz_answers: Mapping[str, Any],
        current_profile: Mapping[str, Any] | None = None,
        extra_context: str | None = None,
    ) -> UserProfileModel:
        """Формирует профиль на основе квиза и существующих данных."""

        if not quiz_answers and not current_profile and not extra_context:
            msg = "Недостаточно данных для генерации профиля"
            logger.error(msg)
            raise ValueError(msg)

        messages = self._build_messages(
            quiz_answers=quiz_answers,
            current_profile=current_profile,
            extra_context=extra_context,
        )
        logger.info("Отправляю запрос к LLM для генерации профиля")
        completion = self._client.chat.completions.parse(
            model=self._model_name,
            messages=messages,
            response_format=UserProfileModel,
            temperature=0.2,
        )
        choice = completion.choices[0]
        message = choice.message
        profile = message.parsed
        if profile is None:
            logger.error("LLM не вернула структурированный профиль: %s", message)
            raise RuntimeError("LLM не вернула профиль")
        logger.info("Профиль успешно сформирован")
        return profile


    @staticmethod
    def _build_messages(
        *,
        quiz_answers: Mapping[str, Any],
        current_profile: Mapping[str, Any] | None,
        extra_context: str | None,
    ) -> list[dict[str, Any]]:
        """Готовит сообщения для LLM."""

        user_payload = {
            "quiz_answers": quiz_answers,
            "current_profile": current_profile or None,
            "extra_context": extra_context or "",
            "task": (
                "Создай новый профиль" if not current_profile else "Аккуратно дообогати профиль"
            ),
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]


def enrich_user_profile(
    *,
    user_id: UUID,
    quiz_answers: Mapping[str, Any],
    extra_context: str | None = None,
    service: ProfileEnrichmentService | None = None,
) -> UserProfileModel:
    """Генерирует профиль и сохраняет его в таблице users."""

    service = service or ProfileEnrichmentService()
    user = users.get_by_id(user_id)
    if user is None:
        msg = f"Пользователь {user_id} не найден"
        logger.error(msg)
        raise LookupError(msg)

    logger.info("Старт обновления profile_json для user_id=%s", user_id)
    profile = service.generate_profile(
        quiz_answers=quiz_answers,
        current_profile=user.profile_json,
        extra_context=extra_context,
    )
    users.update_profile(user_id, profile.model_dump())
    logger.info("profile_json обновлён для user_id=%s", user_id)
    return profile


@dataclass
class EnsureProfileResult:
    """Результат проверки профиля пользователя."""

    enriched: bool
    profile: dict[str, Any]


def ensure_profile_for_user(
    *,
    user_id: UUID,
    force: bool = False,
    extra_context: str | None = None,
) -> EnsureProfileResult:
    """
    Проверяет, заполнен ли профиль пользователя, и при необходимости запускает обогащение.

    Returns:
        EnsureProfileResult: enriched=True, если профиль был обновлён; profile — итоговый JSON.
    Raises:
        LookupError: если пользователь не найден.
        ValueError: если нет завершённого квиза для генерации профиля.
    """

    user = users.get_by_id(user_id)
    if user is None:
        msg = f"Пользователь {user_id} не найден"
        logger.error(msg)
        raise LookupError(msg)

    has_profile = bool(user.profile_json)
    if has_profile and not force:
        logger.info("profile_json уже заполнен user_id=%s, обновление не требуется", user_id)
        return EnsureProfileResult(enriched=False, profile=user.profile_json)

    quiz = user_memory.get_quiz_profile(user_id)
    if quiz is None or not quiz.completed or not quiz.answers:
        msg = "Quiz profile is missing or incomplete"
        logger.error(msg)
        raise ValueError(msg)

    quiz_answers = {
        question_id: answer.model_dump(mode="json")
        for question_id, answer in quiz.answers.items()
    }
    context = extra_context or f"Quiz version: {quiz.version}, completed_at: {quiz.completed_at}"
    profile = enrich_user_profile(
        user_id=user_id,
        quiz_answers=quiz_answers,
        extra_context=context,
    )
    return EnsureProfileResult(enriched=True, profile=profile.model_dump())


if __name__ == "__main__":
    import os

    demo_user_id = "469a0f1d-01de-4340-8e8d-e5897eb43d52"
    user_id_value = os.getenv("VMESTE_DEMO_USER_ID", demo_user_id)
    target_user_id = UUID(user_id_value)

    quiz_profile = user_memory.get_quiz_profile(target_user_id)
    if quiz_profile is None or not quiz_profile.answers:
        print("Для указанного пользователя нет сохранённых ответов квиза.")
    else:
        quiz_answers = {
            question_id: answer.model_dump(mode="json")
            for question_id, answer in quiz_profile.answers.items()
        }
        extra_context = (
            f"Quiz version: {quiz_profile.version}, completed_at: {quiz_profile.completed_at}"
        )
        profile = enrich_user_profile(
            user_id=target_user_id,
            quiz_answers=quiz_answers,
            extra_context=extra_context,
        )
        print(profile.model_dump_json(indent=2))
