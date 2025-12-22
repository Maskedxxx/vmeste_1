# app/services/diagnostic_workflow.py
# --- agent_meta ---
# role: diagnostic-workflow
# contract: оркестрирует диагностику и рекомендации контента
# owner: backend-core
# --- /agent_meta ---

"""Оркестратор диагностики и блока контентных рекомендаций."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Sequence, Tuple
from uuid import UUID

from app.db.repositories import user_memory
from app.models.diagnostic import DiagnosticBundle
from app.models.recommendation import BlockRecommendation
from app.services.diagnostic_agent import run_diagnostic_with_cache
from app.services.recommendation_agent import generate_block_recommendations


BLOCK_ORDER: Tuple[str, str, str] = ("body", "mind", "sex")


def _load_cached_recommendations(user_id: UUID) -> list[BlockRecommendation] | None:
    raw = user_memory.get_diagnostic_recommendations(user_id)
    if not raw:
        return None
    return [BlockRecommendation.model_validate(item) for item in raw]


def _save_recommendations(user_id: UUID, records: Sequence[BlockRecommendation]) -> None:
    user_memory.upsert_diagnostic_recommendations(
        user_id,
        [record.model_dump(mode="json") for record in records],
    )


def run_diagnostic_with_recommendations(
    user_id: UUID,
    *,
    force: bool = False,
) -> tuple[DiagnosticBundle, bool, list[BlockRecommendation], bool]:
    """Параллельно запускает диагностику и подбор контента."""

    cached_recommendations = None if force else _load_cached_recommendations(user_id)

    def _compute_diagnostic() -> tuple[DiagnosticBundle, bool]:
        return run_diagnostic_with_cache(user_id=user_id, force=force)

    def _compute_recommendations() -> tuple[list[BlockRecommendation], bool]:
        if cached_recommendations is not None:
            return cached_recommendations, True
        records = generate_block_recommendations(user_id=user_id, blocks=BLOCK_ORDER)
        _save_recommendations(user_id, records)
        return records, False

    with ThreadPoolExecutor(max_workers=2) as executor:
        diag_future = executor.submit(_compute_diagnostic)
        rec_future = executor.submit(_compute_recommendations)
        bundle, diagnostic_from_cache = diag_future.result()
        recommendations, rec_from_cache = rec_future.result()

    return bundle, diagnostic_from_cache, recommendations, rec_from_cache


__all__ = ["run_diagnostic_with_recommendations"]
