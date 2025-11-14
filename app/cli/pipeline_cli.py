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
from app.services.diagnostic_agent import run_diagnostic_with_cache
from app.services.profile_enrichment import ensure_profile_for_user
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
    if "profile_enriched" in summary:
        print(f"Профиль обновлён сейчас: {'да' if summary['profile_enriched'] else 'нет'}")
    if "profile_error" in summary:
        print(f"Ошибка профиля: {summary['profile_error']}")
    if "diagnostic_from_cache" in summary:
        print(f"Диагностика из кэша: {'да' if summary['diagnostic_from_cache'] else 'нет'}")


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
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Проверить и при необходимости обогатить profile_json.",
    )
    parser.add_argument(
        "--force-profile",
        action="store_true",
        help="Перегенерировать profile_json даже если он есть.",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Запустить диагностический агент и сохранить результат.",
    )
    parser.add_argument(
        "--force-diagnostic",
        action="store_true",
        help="Перегенерировать диагностику даже если кэш есть.",
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

    if args.profile:
        try:
            profile_result = ensure_profile_for_user(
                user_id=user.user_id,
                force=args.force_profile,
            )
            summary["profile_enriched"] = profile_result.enriched
            summary["profile"] = profile_result.profile
        except ValueError as err:
            summary["profile_error"] = str(err)
            logger.warning("Профиль не обновлён: %s", err)
        except LookupError as err:
            summary["profile_error"] = str(err)
            logger.error("Ошибка поиска пользователя: %s", err)

    if args.diagnostic:
        try:
            bundle, from_cache = run_diagnostic_with_cache(
                user_id=user.user_id,
                force=args.force_diagnostic,
            )
            summary["diagnostic_from_cache"] = from_cache
            summary["diagnostic_bundle"] = bundle.model_dump(mode="json")
        except Exception as err:
            summary["diagnostic_error"] = str(err)
            logger.error("Диагностический агент сообщил ошибку: %s", err)

    _print_summary(summary, args.as_json)


if __name__ == "__main__":
    main()
