# app/services/quiz_service.py
# --- agent_meta ---
# role: quiz-service
# contract: содержит вопросы квиза и валидацию ответов
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - get_quiz_questions() -> list[QuizQuestion]
#   - validate_answers(raw_answers: dict[str, str]) -> QuizResult
# --- /agent_meta ---

"""Сервис квиза: выдаёт вопросы и приводится ответы к единому формату."""

"""
TODO:
- Добавить слой API (например, FastAPI-эндпоинты) или фонового сервиса, который принимает
  ответы от клиента и сохраняет их в user_memory.memory_data (ключ quiz_profile.answers).
- После сохранения автоматически проверять, обогащён ли профиль пользователя
  (`users.profile_json`). Если поле пустое или устарело, запускать агент
  `app/services/profile_enrichment.py` для генерации обновлённого профиля на основе квиза.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Iterable

from app.models import ChoiceOption, QuestionType, QuizAnswer, QuizQuestion, QuizResult


logger = logging.getLogger("vmeste.services.quiz_service")

AGE_PATTERN = re.compile(r"(\d{1,3})")


def get_quiz_questions() -> list[QuizQuestion]:
    """Возвращает список вопросов квиза."""
    return [
        QuizQuestion(
            question_id="age",
            text="Чтобы подобрать упражнения и рекомендации, мне нужно знать твой возраст.",
            helper="Это поможет корректно оценить гормональный фон и этап жизни.",
            question_type=QuestionType.NUMBER,
        ),
        QuizQuestion(
            question_id="gender",
            text="Отлично, теперь уточним пол ⚡️",
            helper="Он нужен, чтобы корректно адаптировать упражнения и рекомендации.",
            question_type=QuestionType.CHOICE,
            options=[
                ChoiceOption(value="male", label="Мужчина"),
                ChoiceOption(value="female", label="Женщина"),
            ],
        ),
        QuizQuestion(
            question_id="relationship_status",
            text="Вы в отношениях?",
            question_type=QuestionType.CHOICE,
            options=[
                ChoiceOption(value="yes", label="Да"),
                ChoiceOption(value="no", label="Нет"),
                ChoiceOption(value="complicated", label="Сложно"),
            ],
        ),
        QuizQuestion(
            question_id="main_concern",
            text="Что вас беспокоит?",
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="sexual_insecurity",
            text=(
                "Что именно вызывает ощущение неполноценности в сексе? "
                "Это связано с оргазмом, желанием, отношениями с партнёром или чем-то другим?"
            ),
            helper="Если трудно сформулировать — поделитесь, что приходит в голову.",
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="problem_duration",
            text=(
                "Как давно вы замечаете эту проблему, и насколько она острая для вас сейчас "
                "(мешает ли наслаждаться жизнью или отношениями)?"
            ),
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="sexual_frequency",
            text="Как часто у вас бывает секс или мастурбация в последнее время?",
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="problem_patterns",
            text="Замечаете ли вы паттерны, когда проблема усиливается (стресс, усталость, тревога)?",
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="health_factors",
            text="Есть ли болезни, операции или боли, которые могли повлиять на секс?",
            helper="Например, в области таза или гормональные нарушения.",
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="attempts_history",
            text=(
                "Что вы уже пробовали, чтобы справиться с этой проблемой? "
                "Обращались ли к специалистам, читали книги, проходили курсы?"
            ),
            question_type=QuestionType.TEXT,
        ),
        QuizQuestion(
            question_id="course_expectations",
            text=(
                "Чего вы ожидаете от курса или рекомендаций? "
                "Предпочтения в упражнениях, формате контента и результатах?"
            ),
            question_type=QuestionType.TEXT,
        ),
    ]


def validate_answers(raw_answers: dict[str, str] | Iterable[QuizAnswer]) -> QuizResult:
    """Преобразует ответы в структуру QuizResult, проверяет возраст и пол."""
    if isinstance(raw_answers, dict):
        answers = [QuizAnswer(question_id=k, value=v.strip()) for k, v in raw_answers.items()]
    else:
        answers = list(raw_answers)

    normalized: list[QuizAnswer] = []
    for answer in answers:
        if answer.question_id == "age":
            normalized.append(QuizAnswer(question_id="age", value=_parse_age(answer.value)))
        elif answer.question_id == "gender":
            normalized.append(QuizAnswer(question_id="gender", value=_normalize_gender(answer.value)))
        else:
            normalized.append(QuizAnswer(question_id=answer.question_id, value=answer.value.strip()))

    return QuizResult(answers=normalized)


def _parse_age(value: str) -> str:
    match = AGE_PATTERN.search(value)
    if not match:
        raise ValueError("Для возраста нужно указать число")
    age = int(match.group(1))
    if age <= 0 or age > 120:
        raise ValueError("Возраст должен быть в диапазоне 1–120")
    return str(age)


def _normalize_gender(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"male", "мужчина", "m"}:
        return "male"
    if normalized in {"female", "женщина", "f"}:
        return "female"
    raise ValueError("Пол нужно выбрать из списка (мужчина/женщина)")


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Проверка сервиса квиза.")
    parser.add_argument("--as-json", action="store_true", help="Вывести ответы в JSON.")
    args = parser.parse_args()

    questions = get_quiz_questions()
    collected: list[QuizAnswer] = []
    print("=== Квиз демо ===")
    for question in questions:
        print()
        print(question.text)
        if question.helper:
            print(question.helper)
        if question.question_type == QuestionType.CHOICE:
            for idx, option in enumerate(question.options, start=1):
                print(f"  {idx}. {option.label}")
        value = _ask_with_validation(question)
        collected.append(QuizAnswer(question_id=question.question_id, value=value))

    result = QuizResult(answers=collected)
    if args.as_json:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    else:
        print("\nОтветы:")
        for answer in result.answers:
            print(f"- {answer.question_id}: {answer.value}")


def _ask_with_validation(question: QuizQuestion) -> str:
    """Спрашивает пользователя до тех пор, пока ответ не пройдет валидацию."""
    while True:
        raw_value = input("> ").strip()
        try:
            normalized = _normalize_choice_if_needed(question, raw_value)
        except ValueError as choice_err:
            print(f"Ошибка: {choice_err}. Попробуйте ещё раз.")
            continue
        try:
            validated = validate_answers([QuizAnswer(question_id=question.question_id, value=normalized)])
            return validated.answers[0].value
        except ValueError as exc:
            print(f"Ошибка: {exc}. Попробуйте ещё раз.")


def _normalize_choice_if_needed(question: QuizQuestion, value: str) -> str:
    """Преобразует ввод для вопросов с вариантами."""
    if question.question_type != QuestionType.CHOICE or not question.options:
        return value

    cleaned = value.strip().lower()
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(question.options):
            return question.options[idx].value
    for option in question.options:
        if cleaned == option.value.lower():
            return option.value
        if cleaned == option.label.lower():
            return option.value
    raise ValueError("нужно выбрать один из предложенных вариантов")


if __name__ == "__main__":
    _cli()
