# app/models/__init__.py
# --- agent_meta ---
# role: domain-models
# contract: объединяет пользовательские Pydantic-схемы вне слоя БД
# owner: backend-core
# --- /agent_meta ---

"""Пакет доменных моделей (не связан напрямую со схемой БД)."""

from app.models.dialog_summary import DialogSummary
from app.models.diagnostic import BodyInsight, DiagnosticBundle, MindInsight, SexInsight
from app.models.quiz import ChoiceOption, QuestionType, QuizAnswer, QuizQuestion, QuizResult
from app.models.rag_chat import RagReference, RagReply
from app.models.recommendation import ContentCandidate, RecommendationOffer, RecommendationReply
from app.models.therapy import TherapyReply
from app.models.user_profile import UserProfileModel
from app.models.week_plan import PlanItem, WeekPlan

__all__ = [
    "ContentCandidate",
    "RecommendationOffer",
    "RecommendationReply",
    "QuizQuestion",
    "QuizAnswer",
    "QuizResult",
    "QuestionType",
    "ChoiceOption",
    "RagReference",
    "RagReply",
    "UserProfileModel",
    "DialogSummary",
    "TherapyReply",
    "BodyInsight",
    "MindInsight",
    "SexInsight",
    "DiagnosticBundle",
    "PlanItem",
    "WeekPlan",
]
