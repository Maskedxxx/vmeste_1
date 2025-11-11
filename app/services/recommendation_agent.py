# app/services/recommendation_agent.py
# --- agent_meta ---
# role: recommendation-agent
# contract: генерирует персональные рекомендации контента на основе профиля и кандидатов
# owner: backend-core
# last_reviewed: 2025-11-10
# interfaces:
#   - RecommendationAgentService.generate_reply(...)
#   - run_content_recommendation(user_id: UUID, tone_voice: str, limit: int)
# --- /agent_meta ---

"""Агент, который подбирает релевантный контент психолога под профиль пользователя."""

from __future__ import annotations

import json
import logging
from typing import Iterable, Sequence
from uuid import UUID

from openai import OpenAI

from app.db.repositories import psychologist_content, users
from app.models.recommendation import ContentCandidate, RecommendationReply
from app.models.user_profile import UserProfileModel
from config import get_settings


logger = logging.getLogger("vmeste.services.recommendation_agent")

SYSTEM_PROMPT = (
    "Ты агент рекомендаций психологической платформы «Вместе». "
    "Твоя задача — внимательно изучить профиль пользователя, сопоставить его с "
    "переданными материалами психолога и предложить один наиболее подходящий вариант. "
    "Обязательно используй заданный тон общения и объясни, почему материал поможет."
)


class RecommendationAgentService:
    """Работает с OpenAI Chat Completions в режиме parse."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model_name = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate_reply(
        self,
        *,
        profile: UserProfileModel,
        candidates: Sequence[ContentCandidate],
        tone_voice: str,
    ) -> RecommendationReply:
        """Возвращает персонализированную рекомендацию."""

        if not candidates:
            msg = "Нет кандидатов для рекомендации"
            logger.error(msg)
            raise ValueError(msg)

        messages = self._build_messages(profile=profile, candidates=candidates, tone_voice=tone_voice)
        logger.info("Отправляю запрос к LLM для агента рекомендаций (кандидатов=%s)", len(candidates))
        completion = self._client.chat.completions.parse(
            model=self._model_name,
            messages=messages,
            response_format=RecommendationReply,
            temperature=0.4,
        )
        reply = completion.choices[0].message.parsed
        if reply is None:
            logger.error("LLM не вернула структурированный ответ: %s", completion)
            raise RuntimeError("LLM не вернула ответ рекомендаций")
        logger.info("Ответ агента рекомендаций сформирован")
        return reply

    @staticmethod
    def _build_messages(
        *,
        profile: UserProfileModel,
        candidates: Sequence[ContentCandidate],
        tone_voice: str,
    ) -> list[dict[str, str]]:
        """Готовит сообщения для LLM."""

        user_payload = {
            "tone_voice": tone_voice,
            "user_profile": profile.model_dump(mode="json"),
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "instructions": (
                "Выбери один материал, который лучше всего отвечает потребностям пользователя. "
                "Если кандидаты слабо подходят, всё равно выбери ближайший и объясни, почему он полезен."
            ),
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]


def _load_profile(user_id: UUID) -> UserProfileModel:
    """Загружает profile_json и приводит к UserProfileModel."""

    user = users.get_by_id(user_id)
    if user is None:
        msg = f"Пользователь {user_id} не найден"
        logger.error(msg)
        raise LookupError(msg)
    profile_raw = user.profile_json or {}
    try:
        return UserProfileModel.model_validate(profile_raw)
    except Exception:
        logger.warning("profile_json user_id=%s не соответствует схеме, используем значения по умолчанию", user_id)
        return UserProfileModel()


def _load_candidates(limit: int) -> list[ContentCandidate]:
    """Получает список кандидатов из таблицы psychologist_content."""

    rows = psychologist_content.list_available(limit=limit)
    candidates: list[ContentCandidate] = []
    for row in rows:
        price = row.get("price")
        currency = row.get("currency")
        price_label = None
        if price is not None:
            price_label = f"{price} {currency or 'RUB'}"
        metadata = row.get("metadata") or {}
        duration_minutes = row.get("duration_minutes")
        duration_meta = metadata.get("duration")
        media_hint = None
        if isinstance(duration_meta, str):
            media_hint = duration_meta
        elif duration_meta is not None:
            media_hint = f"Длительность ~{duration_meta} минут"
        elif duration_minutes:
            media_hint = f"Длительность ~{duration_minutes} минут"
        metadata_note = metadata.get("format") or metadata.get("notes")
        if metadata_note is not None:
            metadata_note = str(metadata_note)
        candidate = ContentCandidate(
            content_id=str(row["content_id"]),
            title=row["title"],
            summary=row.get("summary") or metadata.get("summary", ""),
            topic=row.get("topic"),
            content_type=row.get("content_type"),
            tags=row.get("tags") or [],
            price=price_label,
            media_hint=media_hint,
            metadata_note=metadata_note,
        )
        candidates.append(candidate)
    return candidates


def run_content_recommendation(
    *,
    user_id: UUID,
    tone_voice: str = "gentle",
    limit: int = 5,
    service: RecommendationAgentService | None = None,
) -> RecommendationReply:
    """Готовит входные данные и возвращает ответ агента рекомендаций."""

    profile = _load_profile(user_id)
    if not profile.summary and not profile.key_concerns:
        logger.warning("profile_json для user_id=%s почти пустой — ответ может быть менее точным", user_id)

    candidates = _load_candidates(limit)
    if not candidates:
        raise RuntimeError("В таблице psychologist_content нет доступных материалов")

    service = service or RecommendationAgentService()
    reply = service.generate_reply(profile=profile, candidates=candidates, tone_voice=tone_voice)
    return reply


if __name__ == "__main__":
    import os

    demo_user_id = os.getenv("VMESTE_DEMO_USER_ID", "469a0f1d-01de-4340-8e8d-e5897eb43d52")
    reply = run_content_recommendation(user_id=UUID(demo_user_id), tone_voice="gentle", limit=5)
    print(reply.model_dump_json(indent=2))
