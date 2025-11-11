# app/services/therapy_agent.py
# --- agent_meta ---
# role: therapy-agent
# contract: формирует эмпатичный ответ поддержки на основе профиля, памяти и недавнего диалога
# owner: backend-core
# last_reviewed: 2025-11-10
# interfaces:
#   - TherapyAgentService.generate_reply(...)
#   - run_therapy_agent(user_id: UUID, history_limit: int = 6)
# --- /agent_meta ---

"""Агент поддержки/терапии: использует профиль, саммари и свежие сообщения."""

from __future__ import annotations

import json
import logging
from typing import Iterable, Sequence
from uuid import UUID

from openai import OpenAI

from app.db.models import ChatMessage, UserMemory
from app.db.repositories import chat_history, user_memory, users
from app.models import DialogSummary, TherapyReply, UserProfileModel
from config import get_settings


logger = logging.getLogger("vmeste.services.therapy_agent")

SYSTEM_PROMPT = (
    "Ты терапевтический агент психологической платформы «Вместе». "
    "Отвечай поддерживающе, мягко уточняй детали, опирайся на профиль и саммари. "
    "Если есть риск-факторы — отметь их и предложи безопасные шаги."
)


class TherapyAgentService:
    """Работает с OpenAI Chat Completions (parse)."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model_name = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate_reply(
        self,
        *,
        profile: UserProfileModel,
        summary: DialogSummary | None,
        recent_messages: Sequence[dict[str, str]],
    ) -> TherapyReply:
        """Возвращает структурированный ответ поддержки."""

        messages = self._build_messages(profile=profile, summary=summary, recent_messages=recent_messages)
        completion = self._client.chat.completions.parse(
            model=self._model_name,
            messages=messages,
            response_format=TherapyReply,
            temperature=0.3,
        )
        reply = completion.choices[0].message.parsed
        if reply is None:
            raise RuntimeError("LLM не вернула ответ терапевта")
        return reply

    @staticmethod
    def _build_messages(
        *,
        profile: UserProfileModel,
        summary: DialogSummary | None,
        recent_messages: Sequence[dict[str, str]],
    ) -> list[dict[str, str]]:
        payload = {
            "user_profile": profile.model_dump(mode="json"),
            "dialog_summary": summary.model_dump(mode="json") if summary else None,
            "recent_messages": list(recent_messages),
            "instructions": (
                "Ответь на последнюю реплику пользователя. "
                "Поддержи, дай максимум 2 мягкие рекомендации или техники. "
                "Всегда завершай вопросом, который помогает продолжить разговор."
            ),
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]


def _load_profile(user_id: UUID) -> UserProfileModel:
    user = users.get_by_id(user_id)
    if user is None:
        raise LookupError(f"Пользователь {user_id} не найден")
    try:
        return UserProfileModel.model_validate(user.profile_json or {})
    except Exception:
        logger.warning("profile_json user_id=%s повреждён, возвращаю пустой профиль", user_id)
        return UserProfileModel()


def _load_summary(user_id: UUID) -> DialogSummary | None:
    memory = user_memory.get_memory(user_id)
    if memory is None:
        return None
    summary_raw = memory.memory_data.get("dialog_summary")
    if not summary_raw:
        return None
    try:
        return DialogSummary.model_validate(summary_raw)
    except Exception:
        logger.warning("dialog_summary user_id=%s имеет неверный формат, пропускаю", user_id)
        return None


def _load_recent_messages(user_id: UUID, limit: int) -> list[dict[str, str]]:
    messages: Iterable[ChatMessage] = chat_history.list_by_user(user_id, limit=limit)
    prepared: list[dict[str, str]] = []
    for message in reversed(list(messages)):
        payload = message.payload or {}
        text = payload.get("text")
        if not text:
            continue
        prepared.append(
            {
                "role": message.sender,
                "text": text,
                "timestamp": (message.response_timestamp or message.request_timestamp).isoformat(),
            }
        )
    return prepared[-limit:]


def run_therapy_agent(
    *,
    user_id: UUID,
    history_limit: int = 6,
    service: TherapyAgentService | None = None,
) -> TherapyReply:
    """Подготавливает данные и запускает агента."""

    profile = _load_profile(user_id)
    summary = _load_summary(user_id)
    recent_messages = _load_recent_messages(user_id, limit=history_limit)
    if not recent_messages:
        raise RuntimeError("Нет сообщений, чтобы построить терапевтический ответ")

    logger.info("Запускаю терапевтический агент для user_id=%s", user_id)
    service = service or TherapyAgentService()
    reply = service.generate_reply(profile=profile, summary=summary, recent_messages=recent_messages)
    return reply


if __name__ == "__main__":
    import os

    demo_user_id = os.getenv("VMESTE_DEMO_USER_ID", "469a0f1d-01de-4340-8e8d-e5897eb43d52")
    result = run_therapy_agent(user_id=UUID(demo_user_id))
    print(result.model_dump_json(indent=2))
