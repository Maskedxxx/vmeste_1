# app/db/repositories/__init__.py
# --- agent_meta ---
# role: repositories-package
# contract: собирает репозитории для работы с БД
# owner: backend-core
# --- /agent_meta ---

"""Пакет с репозиториями для работы с БД."""

from app.db.repositories import (
    chat_history,
    chunk_embeddings_meta,
    content_chunks,
    documents,
    psychologist_content,
    sessions,
    sources,
    user_memory,
    users,
)

__all__ = [
    "chat_history",
    "chunk_embeddings_meta",
    "content_chunks",
    "documents",
    "psychologist_content",
    "sessions",
    "sources",
    "user_memory",
    "users",
]
