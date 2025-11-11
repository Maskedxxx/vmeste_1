# app/services/dialog_summary.py
# --- agent_meta ---
# role: dialog-summary-service
# contract: генерирует структурированное саммари диалога и сохраняет его в user_memory
# owner: backend-core
# last_reviewed: 2025-11-10
# interfaces:
#   - DialogSummaryService.generate(...)
#   - summarize_dialog(user_id: UUID, session_id: UUID | None, limit: int)
# --- /agent_meta ---

"""LLM-сервис для генерации саммари диалогов."""

from __future__ import annotations

import logging
from typing import Iterable
from uuid import UUID

from openai import OpenAI

from app.db.models import ChatMessage, UserMemoryUpsert
from app.db.repositories import chat_history, user_memory
from app.models import DialogSummary
from config import get_settings


logger = logging.getLogger("vmeste.services.dialog_summary")

SYSTEM_PROMPT = (
    "Ты аналитик беседы психологической платформы «Вместе». "
    "Получишь историю сообщений между пользователем и ассистентом. "
    "Выдели ключевые факты, эмоции и запланированные шаги и верни структурированное саммари."
    "Не пиши лишнего, если данных нет — оставь поля пустыми."
)


class DialogSummaryService:
    """Вызывает LLM для формирования саммари."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model_name = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate(self, history: Iterable[dict[str, str]]) -> DialogSummary:
        """Создаёт саммари по переданной истории."""

        messages = self._build_messages(history)
        completion = self._client.chat.completions.parse(
            model=self._model_name,
            messages=messages,
            response_format=DialogSummary,
            temperature=0.2,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("LLM не вернула саммари")
        return parsed

    @staticmethod
    def _build_messages(history: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        serialized = []
        for item in history:
            serialized.append(f"{item['role']}: {item['text']}")
        joined = "\n".join(serialized)
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": joined},
        ]


def _format_history(records: Iterable[ChatMessage]) -> list[dict[str, str]]:
    """Готовит историю в формате {role, text} для LLM."""

    items: list[dict[str, str]] = []
    for record in records:
        payload = record.get("payload", {})
        text = payload.get("text")
        if not text:
            continue
        items.append({"role": record.get("sender", "user"), "text": text})
    return items


def summarize_dialog(
    *,
    user_id: UUID,
    session_id: UUID | None = None,
    limit: int = 50,
    service: DialogSummaryService | None = None,
) -> DialogSummary:
    """Создаёт саммари по истории и сохраняет его в user_memory."""

    logger.info("Строю саммари user_id=%s session_id=%s", user_id, session_id)
    if session_id:
        records = chat_history.list_by_session(session_id, limit=limit)
    else:
        records = chat_history.list_by_user(user_id, limit=limit)
    history_payload = _format_history(records)
    if not history_payload:
        raise RuntimeError("Нет сообщений для саммари")

    service = service or DialogSummaryService()
    summary = service.generate(history_payload)

    logger.info("Сохраняю саммари в user_memory")
    memory = user_memory.get_memory(user_id)
    memory_data = dict(memory.memory_data) if memory else {}
    summary_payload = summary.model_dump(mode="json")
    memory_data["dialog_summary"] = summary_payload
    user_memory.upsert_memory(UserMemoryUpsert(user_id=user_id, memory_data=memory_data))
    return summary


if __name__ == "__main__":
    import os

    demo_user_id = os.getenv("VMESTE_DEMO_USER_ID")
    if not demo_user_id:
        print("Укажите VMESTE_DEMO_USER_ID и запустите модуль повторно.")
    else:
        result = summarize_dialog(user_id=UUID(demo_user_id))
        print(result.model_dump_json(indent=2, ensure_ascii=False))
