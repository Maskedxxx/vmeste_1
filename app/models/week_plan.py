# app/models/week_plan.py
# --- agent_meta ---
# role: week-plan-models
# contract: описывает структуру плана на 7 дней
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - PlanItem
#   - WeekPlan
# --- /agent_meta ---

"""Pydantic-схемы для недельного плана."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    """Один день плана."""

    day: int = Field(..., ge=1, le=7, description="Номер дня (1-7).")
    content_id: str = Field(..., description="Материал psychologist_content.")
    title: str = Field(..., description="Название активности/материала.")
    goal: str = Field(..., description="Зачем выполнять этот шаг.")
    instructions: str = Field(..., description="Краткая инструкция или сценарий выполнения.")
    tags: list[str] = Field(default_factory=list, description="Теги, связанные с задачей.")


class WeekPlan(BaseModel):
    """План на неделю."""

    days: list[PlanItem] = Field(..., min_length=7, max_length=7, description="Ровно 7 элементов плана.")
