# app/models/__init__.py
# --- agent_meta ---
# role: domain-models
# contract: объединяет пользовательские Pydantic-схемы вне слоя БД
# owner: backend-core
# --- /agent_meta ---

"""Пакет доменных моделей (не связан напрямую со схемой БД)."""

from app.models.dialog_summary import DialogSummary
from app.models.recommendation import ContentCandidate, RecommendationOffer, RecommendationReply
from app.models.user_profile import UserProfileModel

__all__ = [
    "ContentCandidate",
    "RecommendationOffer",
    "RecommendationReply",
    "UserProfileModel",
    "DialogSummary",
]
