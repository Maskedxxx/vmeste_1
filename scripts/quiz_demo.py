# scripts/quiz_demo.py
# --- agent_meta ---
# role: cli-demo
# contract: интерактивный квиз по отношениям в семье и сохранение ответов
# owner: backend-core
# --- /agent_meta ---

"""CLI-сценарий, работающий через HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
from typing import Final

import requests


QUESTIONS: Final[list[tuple[str, str]]] = [
    (
        "family_closeness",
        "Как вы описали бы текущую близость с семьёй?",
    ),
    (
        "communication_quality",
        "Что помогает или мешает вам открыто разговаривать с близкими?",
    ),
    (
        "conflict_resolution",
        "Как вы обычно решаете семейные конфликты?",
    ),
    (
        "support_expectations",
        "Какой поддержки вам сейчас больше всего не хватает?",
    ),
    (
        "shared_rituals",
        "Есть ли семейные ритуалы, которые хотелось бы восстановить?",
    ),
]


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _prompt_email() -> str:
    email = input("Введите email пользователя: ").strip()
    if not email:
        print("Email обязателен", file=sys.stderr)
        sys.exit(1)
    return email


def _api_request(method: str, path: str, **kwargs):
    url = f"{API_BASE_URL}{path}"
    response = requests.request(method, url, timeout=30, **kwargs)
    if response.status_code >= 400:
        print("API error", response.status_code, response.text, file=sys.stderr)
        response.raise_for_status()
    if response.content:
        return response.json()
    return None


def _get_or_create_user(email: str) -> dict:
    response = requests.get(
        f"{API_BASE_URL}/users/email/{email}", timeout=30
    )
    if response.status_code == 200:
        user = response.json()
        print(f"Найден пользователь {email} (id={user['user_id']})")
        return user
    if response.status_code != 404:
        print("API error", response.status_code, response.text, file=sys.stderr)
        response.raise_for_status()
    payload = {
        "external_id": email,
        "email": email,
        "profile_json": {},
    }
    user = _api_request("post", "/users", json=payload)
    print(f"Создан новый пользователь {email} (id={user['user_id']})")
    return user


def _collect_answers() -> dict[str, dict[str, str]]:
    answers: dict[str, dict[str, str]] = {}
    now = datetime.now(timezone.utc).isoformat()
    print("\nОтветьте, пожалуйста, на 5 вопросов о семейных отношениях.\n")
    for question_id, prompt in QUESTIONS:
        value = input(f"{prompt}\n> ").strip()
        answers[question_id] = {
            "value": value,
            "updated_at": now,
        }
    return answers


def main() -> None:
    print("=== Семейный квиз: демонстрация ===")
    email = _prompt_email()
    user = _get_or_create_user(email)

    profile = _api_request("get", f"/users/{user['user_id']}/quiz-profile")
    if profile and profile.get("completed"):
        completed_at = profile.get("completed_at") or "неизвестно"
        print(
            "Квиз уже заполнен, вопросы пропущены."
            f" Последнее прохождение: {completed_at}."
        )
        return

    answers = _collect_answers()
    completed_at = datetime.now(timezone.utc).isoformat()
    quiz_update = {
        "version": "family_v1",
        "completed": True,
        "completed_at": completed_at,
        "answers": answers,
    }
    updated_profile = _api_request(
        "put",
        f"/users/{user['user_id']}/quiz-profile",
        json=quiz_update,
    )
    print("\nКвиз сохранён. Статус:")
    print(f"  Пользователь: {email}")
    print(f"  Версия: {updated_profile.get('version')}")
    print(
        "  Завершён:",
        "да" if updated_profile.get("completed") else "нет",
        ", время: ",
        updated_profile.get("completed_at"),
    )


if __name__ == "__main__":
    main()
