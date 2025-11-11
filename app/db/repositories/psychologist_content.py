# app/db/repositories/psychologist_content.py
# --- agent_meta ---
# role: psychologist-content-repository
# contract: выборки материалов психолога для рекомендаций
# owner: backend-core
# --- /agent_meta ---

"""Репозиторий для таблицы psychologist_content."""

from __future__ import annotations

import logging
from typing import Any

from app.db.connection import fetch_all


logger = logging.getLogger("vmeste.db.repositories.psychologist_content")


def list_available(limit: int = 5) -> list[dict[str, Any]]:
    """Возвращает список активных материалов с базовыми полями."""

    logger.debug("Загрузка материалов психолога, limit=%s", limit)
    query = """
        SELECT
            content_id,
            title,
            summary,
            topic,
            content_type,
            tags,
            price,
            currency,
            duration_minutes,
            metadata
        FROM psychologist_content
        WHERE available = TRUE
          AND is_deleted = FALSE
        ORDER BY updated_at DESC
        LIMIT %(limit)s
    """
    rows = fetch_all(query, {"limit": limit})
    return rows


__all__ = ["list_available"]
