#!/usr/bin/env python3
# scripts/chat_cli.py
# --- agent_meta ---
# role: chat-cli
# contract: интерактивный CLI для общения с LLM и записью истории в API
# owner: backend-core
# --- /agent_meta ---

"""Интерактивный CLI для проверки API через реальный LLM (OpenAI).

Перед запуском:
    export OPENAI_API_KEY=...
    export VMESTE_API_URL=http://localhost:8000  # при необходимости
    pip install -r requirements.txt
    uvicorn app.main:app --reload  # или docker compose up

Запуск:
    python scripts/chat_cli.py

Команды:
    /exit    — завершить сессию
    /history — вывести историю текущей сессии из API
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from uuid import UUID, uuid4

import requests
from openai import OpenAI


BASE_URL = os.getenv("VMESTE_API_URL", "http://localhost:8000")
REQUEST_TIMEOUT = float(os.getenv("VMESTE_API_TIMEOUT", "150"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
HISTORY_LIMIT = int(os.getenv("VMESTE_HISTORY_LIMIT", "40"))
SYSTEM_PROMPT = os.getenv(
    "VMESTE_SYSTEM_PROMPT",
    (
        "Ты эмпатичный ассистент психологической платформы «Вместе». "
        "Отвечай поддерживающе, задавай уточняющие вопросы и предлагай мягкие рекомендации.\n\n"
        "ВАЖНО: У тебя есть доступ к истории предыдущих разговоров с этим пользователем. "
        "Всегда учитывай ранее обсужденные темы, проблемы и контекст. "
        "Если пользователь упоминал свою ситуацию ранее — обращайся к этой информации. "
        "Проявляй непрерывность и последовательность в поддержке."
    ),
)


def fatal(message: str) -> None:
    """Печатает ошибку и завершает программу."""
    print(f"Ошибка: {message}", file=sys.stderr)
    sys.exit(1)


def call_api(method: str, path: str, **kwargs: Any) -> requests.Response:
    """Отправляет запрос к нашему API."""
    url = f"{BASE_URL}{path}"
    response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    try:
        response.raise_for_status()
    except requests.HTTPError:
        detail = response.text
        fatal(f"API вернул ошибку {response.status_code}: {detail}")
    return response


def ensure_user(email: str) -> dict[str, Any]:
    """Создаёт пользователя (external_id = email) или возвращает существующего."""
    payload = {
        "external_id": email,
        "email": email,
        "profile_json": {"demo": True},
    }
    return call_api("POST", "/users", json=payload).json()


def create_session(user_id: UUID, mode: str = "intake") -> dict[str, Any]:
    """Создаёт новую сессию."""
    payload = {"user_id": str(user_id), "mode": mode}
    return call_api("POST", "/sessions", json=payload).json()


def add_message(session_id: UUID, user_id: UUID, sender: str, text: str) -> dict[str, Any]:
    """Записывает сообщение в историю чата."""
    payload = {
        "user_id": str(user_id),
        "sender": sender,
        "message_type": "text",
        "payload": {"text": text},
    }
    return call_api("POST", f"/sessions/{session_id}/messages", json=payload).json()


def fetch_session_history(session_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
    """Возвращает историю указанной сессии (для команды /history)."""
    response = call_api("GET", f"/sessions/{session_id}/messages", params={"limit": limit})
    messages = response.json()
    return [message_to_entry(item) for item in messages]


def load_memory_history(user_id: UUID, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
    """Загружает conversation_history из user_memory."""
    response = call_api("GET", f"/users/{user_id}/memory")
    raw = response.json()
    if not raw:
        return []
    history = raw.get("memory_data", {}).get("conversation_history", [])
    return history[-limit:]


def close_session(session_id: UUID, status_value: str = "completed") -> dict[str, Any]:
    """Закрывает сессию."""
    payload = {"status": status_value}
    return call_api("POST", f"/sessions/{session_id}/close", json=payload).json()


def message_to_entry(message: dict[str, Any]) -> dict[str, Any]:
    """Преобразует структуру chat_history в запись памяти."""
    return {
        "role": message.get("sender", "user"),
        "message_type": message.get("message_type", "text"),
        "payload": message.get("payload", {}),
        "timestamp": message.get("response_timestamp") or message.get("request_timestamp"),
    }


def build_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Преобразует историю в формат, который понимает OpenAI Responses API."""
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-HISTORY_LIMIT:]:
        payload = item.get("payload", {})
        text = payload.get("text")
        if not text:
            continue
        role = item.get("role", "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        messages.append({"role": role, "content": text})
    return messages


def run_cli() -> None:
    """Основной цикл общения."""
    api_key = "OPENAI_API_KEY_REDACTED"

    client = OpenAI(api_key=api_key)

    print("=== Vmeste CLI ===")
    print("Команда /exit завершает диалог, /history покажет записи из API.")
    email = input("Введите email пользователя (Enter для нового): ").strip()
    if not email:
        email = f"cli-demo-{uuid4()}@example.com"
        print(f"Использую email: {email}")

    user_data = ensure_user(email)
    user_id = UUID(user_data["user_id"])
    session = create_session(user_id)
    session_id = UUID(session["session_id"])
    print(f"Создана сессия {session_id}")

    history_cache: list[dict[str, Any]] = load_memory_history(user_id)
    print(f"\n[DEBUG] Загружено {len(history_cache)} сообщений из памяти пользователя")
    if history_cache:
        print("[DEBUG] Первые 20 сообщения из истории:")
        for i, msg in enumerate(history_cache[:20]):
            role = msg.get("role", "unknown")
            text = msg.get("payload", {}).get("text", "???")[:5000]
            print(f"  {i+1}. {role}: {text}...")

    try:
        while True:
            user_text = input("Вы: ").strip()
            if not user_text:
                continue
            if user_text == "/exit":
                break
            if user_text == "/history":
                entries = fetch_session_history(session_id)
                print(json.dumps(entries, ensure_ascii=False, indent=2))
                continue

            user_message = add_message(session_id, user_id, "user", user_text)
            user_entry = message_to_entry(user_message)
            history_cache.append(user_entry)

            messages = build_messages(history_cache)
            print(f"\n[DEBUG] Отправляем {len(messages)} сообщений в LLM (включая system prompt)")
            print("[DEBUG] Последние 3 сообщения в контексте:")
            for msg in messages[-30:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "???")[:6000]
                print(f"  - {role}: {content}...")

            response = client.responses.create(
                model=OPENAI_MODEL,
                input=messages,
                max_output_tokens=400,
            )
            assistant_text = response.output_text
            print(f"Ассистент: {assistant_text}")

            assistant_message = add_message(session_id, user_id, "assistant", assistant_text)
            assistant_entry = message_to_entry(assistant_message)
            history_cache.append(assistant_entry)
    finally:
        final_session = close_session(session_id)
        print("Сессия закрыта со статусом:", final_session["status"])
        print("История сохранена, можно проверить таблицы chat_history и user_memory.")


if __name__ == "__main__":
    run_cli()
