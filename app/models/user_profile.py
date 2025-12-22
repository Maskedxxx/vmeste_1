# app/models/user_profile.py
# --- agent_meta ---
# role: user-profile-schema
# contract: описывает структуру profile_json для генерации LLM
# owner: backend-core
# --- /agent_meta ---

"""Pydantic-схема структурированного профиля пользователя."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StressLevel = Literal["low", "moderate", "high", "critical"]
MotivationTrend = Literal["growing", "stable", "declining", "unknown"]


class UserProfileModel(BaseModel):
    """Структура profile_json, которую генерирует LLM."""

    stress_level: StressLevel | None = Field(
        default=None,
        description="Оценка общего уровня стресса пользователя.",
    )
    emotional_tone: str | None = Field(
        default=None,
        description="Краткое описание эмоционального состояния и доминирующих чувств.",
    )
    key_concerns: list[str] = Field(
        default_factory=list,
        description="Основные темы и проблемы, которые пользователь поднимает чаще всего.",
    )
    support_needs: list[str] = Field(
        default_factory=list,
        description="Какая поддержка и форматы помощи нужны (например, упражнения, разговоры).",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Ресурсы или сильные стороны пользователя, на которые можно опираться.",
    )
    motivation_trend: MotivationTrend = Field(
        default="unknown",
        description="Динамика мотивации: растёт, стабильна, снижается или неизвестна.",
    )
    tov_style_tag: str = Field(
        default="gentle",
        description="Предпочитаемый тон общения (например, gentle, coaching, direct).",
    )
    recommended_focus: list[str] = Field(
        default_factory=list,
        description="Темы и направления работы, которые желательно прорабатывать дальше.",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Тревожные маркеры или ситуации, требующие особого внимания.",
    )
    summary: str | None = Field(
        default=None,
        description="Свободный текст с кратким выводом по пользователю.",
    )

