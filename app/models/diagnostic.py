# app/models/diagnostic.py
# --- agent_meta ---
# role: diagnostic-models
# contract: описывает структурированные ответы для диагностики (тело/психика/сексология)
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - BodyInsight
#   - MindInsight
#   - SexInsight
#   - DiagnosticBundle
# --- /agent_meta ---

"""Pydantic-схемы для диагностического агента."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BodyInsight(BaseModel):
    """Диагностический ответ по блоку «тело»."""

    analysis: str = Field(..., description="3–4 предложения с обзором состояния.")
    recommended_doctors: list[str] = Field(
        default_factory=list,
        description="Список специалистов или клиник, куда стоит обратиться.",
    )
    recommended_tests: list[str] = Field(
        default_factory=list,
        description="Анализы или обследования, которые стоит пройти.",
    )
    possible_physiology: list[str] = Field(
        default_factory=list,
        description="Физиологические факторы или гипотезы.",
    )
    tags: list[str] = Field(
        ...,
        description="Теги, описывающие состояние тела (5–6 штук).",
        min_length=5,
        max_length=6,
    )


class MindInsight(BaseModel):
    """Диагностический ответ по блоку «психика»."""

    analysis: str = Field(..., description="Краткий анализ проблемы (3–4 предложения).")
    tags: list[str] = Field(
        ...,
        description="Список тегов, характеризующих проблему (5–6 штук).",
        min_length=5,
        max_length=6,
    )


class SexInsight(BaseModel):
    """Диагностический ответ по блоку «сексология»."""

    analysis: str = Field(..., description="Краткий анализ по сексуальной сфере.")
    tags: list[str] = Field(
        ...,
        description="Теги, описывающие проблему (5–6 штук).",
        min_length=5,
        max_length=6,
    )


class DiagnosticBundle(BaseModel):
    """Полный ответ агента: тело, психика, сексология."""

    body: BodyInsight
    mind: MindInsight
    sex: SexInsight
