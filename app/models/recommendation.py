# app/models/recommendation.py
# --- agent_meta ---
# role: recommendation-models
# contract: схемы кандидатов контента и ответа агента рекомендаций
# owner: backend-core
# --- /agent_meta ---

"""Pydantic-схемы для агента рекомендаций контента."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContentCandidate(BaseModel):
    """Описание материала психолога, который можно порекомендовать."""

    content_id: str = Field(..., description="Идентификатор записи psychologist_content.")
    title: str = Field(..., description="Название материала, отображаемое пользователю.")
    summary: str = Field(..., description="Краткое описание пользы или формата.")
    url: str | None = Field(default=None, description="Ссылка на материал или лендинг.")
    topic: str | None = Field(default=None, description="Основная тема материала.")
    content_type: str | None = Field(default=None, description="Тип контента: lesson/webinar/post/etc.")
    tags: list[str] = Field(default_factory=list, description="Теги из таблицы psychologist_content.")
    price: str | None = Field(default=None, description="Стоимость и валюта в свободном формате.")
    media_hint: str | None = Field(
        default=None,
        description="Дополнительная информация: длительность, формат.",
    )
    metadata_note: str | None = Field(
        default=None,
        description="Свободный комментарий из metadata (например, формат прохождения).",
    )


class RecommendationOffer(BaseModel):
    """Структура оффера, который вернёт агент."""

    content_id: str = Field(..., description="Материал, который предлагается.")
    title: str = Field(..., description="Как назвать оффер в ответе.")
    why: str = Field(..., description="Почему материал актуален конкретному пользователю.")
    expected_result: str = Field(..., description="Какой эффект пользователь получит после прохождения.")
    cta: str = Field(..., description="Призыв к действию (например, «Начать урок»).")


class RecommendationReply(BaseModel):
    """Итоговый ответ агента рекомендаций."""

    style: Literal["gentle", "coaching", "direct"] = Field(
        default="gentle",
        description="Тон общения, выбранный агентом на основе профиля.",
    )
    message: str = Field(..., description="Основной эмпатичный ответ с контекстом пользователя.")
    offer: RecommendationOffer = Field(..., description="Основное предложение контента.")
    follow_up_question: str = Field(
        ...,
        description="Один короткий вопрос, чтобы поддержать контакт после рекомендации.",
    )


class BlockRecommendation(BaseModel):
    """Рекомендация контента для конкретного диагностического блока."""

    block: Literal["body", "mind", "sex"] = Field(..., description="Блок диагностики.")
    recommendation: RecommendationReply = Field(..., description="Ответ агента рекомендаций.")
    content: ContentCandidate = Field(..., description="Карточка контента из каталога.")
