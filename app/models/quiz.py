# app/models/quiz.py
# --- agent_meta ---
# role: quiz-models
# contract: схемы вопросов и ответов для квиза
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - QuizQuestion
#   - QuizAnswer
#   - QuizResult
# --- /agent_meta ---

"""Pydantic-схемы для квиза первичной диагностики."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QuestionType(str, Enum):
    """Тип вопроса."""

    NUMBER = "number"
    CHOICE = "choice"
    TEXT = "text"


class ChoiceOption(BaseModel):
    """Отображение варианта ответа."""

    value: str = Field(..., description="Машинное значение.")
    label: str = Field(..., description="Отображаемый текст.")


class QuizQuestion(BaseModel):
    """Описание вопроса квиза."""

    question_id: str = Field(..., description="Идентификатор вопроса.")
    text: str = Field(..., description="Текст вопроса.")
    helper: str | None = Field(None, description="Дополнительное пояснение.")
    question_type: QuestionType = Field(QuestionType.TEXT, description="Тип вопроса.")
    options: list[ChoiceOption] = Field(default_factory=list, description="Варианты, если выбор.")


class QuizAnswer(BaseModel):
    """Ответ пользователя на один вопрос."""

    question_id: str
    value: str


class QuizResult(BaseModel):
    """Список ответов пользователя."""

    answers: list[QuizAnswer] = Field(default_factory=list)

    @field_validator("answers")
    @classmethod
    def ensure_unique_ids(cls, answers: list[QuizAnswer]) -> list[QuizAnswer]:
        seen: set[str] = set()
        for answer in answers:
            if answer.question_id in seen:
                raise ValueError(f"Дублируется ответ на {answer.question_id}")
            seen.add(answer.question_id)
        return answers
