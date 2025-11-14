# app/cli/pipeline_cli.py
# --- agent_meta ---
# role: pipeline-cli
# contract: CLI для поэтапной проверки пользовательского пайплайна (entry + quiz)
# owner: backend-core
# last_reviewed: 2025-11-13
# interfaces:
#   - main() -> None
# --- /agent_meta ---

"""CLI для поэтапного тестирования пользовательского пайплайна."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any
from uuid import UUID

from pydantic import EmailStr, TypeAdapter

from app.db.models import QuizProfile, User, UserCreate
from app.db.repositories import user_memory, users
from app.services.quiz_service import run_quiz_for_user


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
logger = logging.getLogger("vmeste.cli.pipeline")
EMAIL_ADAPTER = TypeAdapter(EmailStr)


def _ensure_user(email: str) -> tuple[User, bool]:
    """Возвращает пользователя, создавая его при отсутствии."""
    normalized = _normalize_email(email)
    existing = users.get_by_email(normalized)
    if existing:
        return existing, False
    created = users.create_user(UserCreate(external_id=normalized, email=normalized))
    return created, True


def _normalize_email(email: str) -> str:
    """Проверяет email и приводит к нижнему регистру."""
    validated = EMAIL_ADAPTER.validate_python(email.strip())
    return str(validated).lower()


def _get_quiz_status(user_id: UUID) -> tuple[QuizProfile | None, bool]:
    """Считывает квиз-профиль пользователя."""
    quiz = user_memory.get_quiz_profile(user_id)
    return quiz, bool(quiz and quiz.completed)


def _print_summary(summary: dict[str, Any], as_json: bool) -> None:
    """Выводит статус шага в консоль."""
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print("--- Сводка ---")
    print(f"Пользователь: {summary['email']} ({summary['user_id']})")
    print(f"Новый пользователь: {'да' if summary['is_new'] else 'нет'}")
    print(f"Квиз завершён: {'да' if summary['quiz_completed'] else 'нет'}")
    if "quiz_version" in summary:
        print(f"Версия квиза: {summary['quiz_version']}")
        print("Ответов сохранено:", len(summary.get("quiz_answers", {})))


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description="Пошаговая проверка пайплайна entry -> quiz.")
    parser.add_argument("--email", required=True, help="Email пользователя.")
    parser.add_argument(
        "--quiz",
        action="store_true",
        help="Запустить прохождение квиза (CLI) и сохранить ответы.",
    )
    parser.add_argument(
        "--force-quiz",
        action="store_true",
        help="Переписать ответы, даже если квиз уже завершён.",
    )
    parser.add_argument("--as-json", action="store_true", help="Выводить JSON.")
    args = parser.parse_args()

    user, is_new = _ensure_user(args.email)
    quiz, quiz_completed = _get_quiz_status(user.user_id)

    summary: dict[str, Any] = {
        "user_id": str(user.user_id),
        "email": user.email,
        "is_new": is_new,
        "quiz_completed": quiz_completed,
    }

    if args.quiz:
        if quiz_completed and not args.force_quiz:
            logger.info("Квиз уже завершён, используем сохранённые ответы.")
        else:
            logger.info("Запуск CLI-квиза для user_id=%s", user.user_id)
            quiz = run_quiz_for_user(user.user_id)
            quiz_completed = quiz.completed
        if quiz:
            summary["quiz_version"] = quiz.version
            summary["quiz_answers"] = {
                key: value.model_dump(mode="json") for key, value in quiz.answers.items()
            }
            summary["quiz_completed"] = quiz_completed

    _print_summary(summary, args.as_json)


if __name__ == "__main__":
    main()
