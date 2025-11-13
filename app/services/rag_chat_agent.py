# app/services/rag_chat_agent.py
# --- agent_meta ---
# role: rag-chat-agent
# contract: строит ответ на вопрос пользователя с учётом профиля, истории и RAG-контекста
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - RagChatAgent.generate_reply(...)
#   - run_rag_chat(user_id: UUID, user_message: str, history_limit: int = 4)
# --- /agent_meta ---

"""RAG-агент для ответов на вопросы пользователей по материалам психолога."""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any, Sequence
from uuid import UUID

import chromadb
from openai import OpenAI

from app.db.repositories import chat_history, user_memory, users
from app.models import DialogSummary, RagReference, RagReply, UserProfileModel
from config import get_settings


logger = logging.getLogger("vmeste.services.rag_chat_agent")

SYSTEM_PROMPT = (
    "Ты контентный агент психологической платформы «Вместе». "
    "Отвечай по-русски, дружелюбно, с учётом профиля пользователя. "
    "Опирайся на предоставленные чанки контента, кратко цитируй их смысл и объясняй, "
    "почему материал полезен. Если RAG-контекст отсутствует — честно скажи об этом и предложи "
    "универсальные шаги поддержки."
)


class RagChatAgent:
    """Инкапсулирует работу с Chroma и OpenAI для RAG-ответа."""

    def __init__(
        self,
        *,
        chat_model: str | None = None,
        embedding_model: str = "text-embedding-3-large",
        chroma_host: str | None = None,
        chroma_port: int | None = None,
        collection_name: str = "content_all",
        client: OpenAI | None = None,
    ) -> None:
        settings = get_settings()
        self._chat_model = chat_model or getattr(settings, "openai_model", "gpt-4.1-mini")
        self._embedding_model = embedding_model
        self._client = client or OpenAI()

        host = chroma_host or os.getenv("CHROMA_HOST", "localhost")
        port = chroma_port or int(os.getenv("CHROMA_PORT", "8001"))
        chroma_client = chromadb.HttpClient(host=host, port=port)
        self._collection = chroma_client.get_or_create_collection(collection_name)
        logger.info("RAG агент использует коллекцию %s", collection_name)

    def generate_reply(
        self,
        *,
        profile: UserProfileModel,
        summary: DialogSummary | None,
        recent_messages: Sequence[dict[str, str]],
        user_message: str,
    ) -> RagReply:
        """Строит ответ на основе профиля, истории и найденных чанков."""

        payload_texts = list(recent_messages)
        query_text = user_message or _last_user_message(recent_messages)
        if not query_text:
            raise RuntimeError("Нет пользовательского текста для построения RAG-запроса")

        retrieved = self._search_chunks(query_text=query_text, limit=2)
        messages = self._build_messages(
            profile=profile,
            summary=summary,
            recent_messages=payload_texts,
            user_message=user_message,
            references=retrieved,
        )
        completion = self._client.chat.completions.parse(
            model=self._chat_model,
            messages=messages,
            response_format=RagReply,
            temperature=0.4,
        )
        reply = completion.choices[0].message.parsed
        if reply is None:
            raise RuntimeError("LLM не вернула ответ RAG-агента")
        return reply

    def _search_chunks(self, *, query_text: str, limit: int) -> list[RagReference]:
        embedding = self._client.embeddings.create(
            model=self._embedding_model,
            input=query_text,
        ).data[0].embedding

        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=limit,
        )
        ids = result.get("ids", [[]])[0]
        texts = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        references: list[RagReference] = []
        for idx, chunk_id in enumerate(ids):
            if not chunk_id:
                continue
            metadata = metadatas[idx] or {}
            preview = texts[idx][:260].strip() if texts and idx < len(texts) else ""
            references.append(
                RagReference(
                    chunk_id=chunk_id,
                    doc_id=str(metadata.get("doc_id", "")),
                    preview=preview,
                    topic=metadata.get("topic"),
                )
            )
        return references

    @staticmethod
    def _build_messages(
        *,
        profile: UserProfileModel,
        summary: DialogSummary | None,
        recent_messages: Sequence[dict[str, str]],
        user_message: str,
        references: list[RagReference],
    ) -> list[dict[str, str]]:
        payload: dict[str, Any] = {
            "user_profile": profile.model_dump(mode="json"),
            "dialog_summary": summary.model_dump(mode="json") if summary else None,
            "recent_messages": list(recent_messages),
            "current_user_message": user_message,
            "retrieved_chunks": [
                ref.model_dump(mode="json") for ref in references
            ],
            "instructions": (
                "Сформируй ответ по последнему сообщению пользователя. "
                "В тексте сошлись на ключевые идеи найденных материалов и дай 1-2 конкретных шага."
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
    if not memory:
        return None
    raw = memory.memory_data.get("dialog_summary")
    if not raw:
        return None
    try:
        return DialogSummary.model_validate(raw)
    except Exception:
        logger.warning("dialog_summary user_id=%s имеет неверный формат", user_id)
        return None


def _load_recent_messages(user_id: UUID, limit: int) -> list[dict[str, str]]:
    records = chat_history.list_by_user(user_id, limit=limit)
    prepared: list[dict[str, str]] = []
    for record in reversed(records):
        payload = record.payload or {}
        text = payload.get("text")
        if not text:
            continue
        prepared.append(
            {
                "role": record.sender,
                "text": text,
                "timestamp": (record.response_timestamp or record.request_timestamp).isoformat(),
            }
        )
    return prepared[-limit:]


def _last_user_message(messages: Sequence[dict[str, str]]) -> str | None:
    for item in reversed(messages):
        if item.get("role") == "user" and item.get("text"):
            return item["text"]
    return None


def run_rag_chat(
    *,
    user_id: UUID,
    user_message: str,
    history_limit: int = 4,
    service: RagChatAgent | None = None,
) -> RagReply:
    """Подготавливает данные, вызывает RAG-агента и возвращает ответ."""
    profile = _load_profile(user_id)
    summary = _load_summary(user_id)
    recent = _load_recent_messages(user_id, limit=history_limit)
    if user_message:
        recent.append({"role": "user", "text": user_message, "timestamp": "pending"})

    logger.info("RAG-агент стартовал для user_id=%s", user_id)
    service = service or RagChatAgent()
    return service.generate_reply(
        profile=profile,
        summary=summary,
        recent_messages=recent,
        user_message=user_message,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG чат агент (демо-запуск).")
    parser.add_argument("--user-id", type=str, default=os.getenv("VMESTE_DEMO_USER_ID"))
    parser.add_argument(
        "--question",
        type=str,
        required=True,
        help="Текущий вопрос пользователя",
    )
    parser.add_argument("--history", type=int, default=4)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if not args.user_id:
        raise SystemExit("Нужно передать --user-id или установить VMESTE_DEMO_USER_ID")
    reply = run_rag_chat(user_id=UUID(args.user_id), user_message=args.question, history_limit=args.history)
    print(reply.model_dump_json(indent=2))
