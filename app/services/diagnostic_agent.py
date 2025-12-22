# app/services/diagnostic_agent.py
# --- agent_meta ---
# role: diagnostic-agent
# contract: формирует три блока рекомендаций (тело/психика/сексология) по профилю пользователя
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - DiagnosticAgent.generate_bundle(...)
#   - run_diagnostic_agent(user_id: UUID)
# --- /agent_meta ---

"""Агент, который строит диагностические выводы по профилю пользователя."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Tuple
from uuid import UUID

from openai import OpenAI

from app.models import BodyInsight, DiagnosticBundle, MindInsight, SexInsight, UserProfileModel
from app.db.repositories import user_memory, users
from config import get_settings


logger = logging.getLogger("vmeste.services.diagnostic_agent")

SYSTEM_PROMPT_BODY = (
    "Ты эксперт по женскому и мужскому здоровью. "
    "На основе профиля пользователя опиши основные гипотезы по телу (3-4 предложения), "
    "перечисли рекомендуемых врачей/специалистов, предложи анализы и физиологические факторы."
)

SYSTEM_PROMPT_MIND = (
    "Ты психолог-консультант. Сформулируй 3-4 предложения анализа текущей проблемы "
    "и предложи 5-6 тегов (одно-два слова), описывающих психоэмоциональные состояния."
)

SYSTEM_PROMPT_SEX = (
    "Ты сексолог-консультант. Сформулируй 3-4 предложения анализа сексуальной части "
    "и предложи 5-6 тегов, характеризующих основные запросы человека."
)


class DiagnosticAgent:
    """Упрощённый сервис, который последовательно вызывает LLM."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate_bundle(self, profile: UserProfileModel) -> DiagnosticBundle:
        """Генерирует три блока рекомендаций."""
        body = self._call_body(profile)
        mind = self._call_mind(profile)
        sex = self._call_sex(profile)
        return DiagnosticBundle(body=body, mind=mind, sex=sex)

    def _call_body(self, profile: UserProfileModel) -> BodyInsight:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_BODY},
            {"role": "user", "content": json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)},
        ]
        completion = self._client.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=BodyInsight,
            temperature=0.2,
        )
        result = completion.choices[0].message.parsed
        if result is None:
            raise RuntimeError("LLM не вернула блок по телу")
        return result

    def _call_mind(self, profile: UserProfileModel) -> MindInsight:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_MIND},
            {"role": "user", "content": json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)},
        ]
        completion = self._client.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=MindInsight,
            temperature=0.2,
        )
        result = completion.choices[0].message.parsed
        if result is None:
            raise RuntimeError("LLM не вернула блок психики")
        return result

    def _call_sex(self, profile: UserProfileModel) -> SexInsight:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_SEX},
            {"role": "user", "content": json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)},
        ]
        completion = self._client.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=SexInsight,
            temperature=0.2,
        )
        result = completion.choices[0].message.parsed
        if result is None:
            raise RuntimeError("LLM не вернула блок сексологии")
        return result


def _load_profile(user_id: UUID) -> UserProfileModel:
    user = users.get_by_id(user_id)
    if user is None:
        raise LookupError(f"User {user_id} not found")
    try:
        return UserProfileModel.model_validate(user.profile_json or {})
    except Exception:
        logger.warning("profile_json повреждён, возвращаю пустой профиль")
        return UserProfileModel()


def run_diagnostic_agent(user_id: UUID) -> DiagnosticBundle:
    profile = _load_profile(user_id)
    agent = DiagnosticAgent()
    logger.info("Запуск диагностического агента для user_id=%s", user_id)
    return agent.generate_bundle(profile)


def run_diagnostic_with_cache(user_id: UUID, *, force: bool = False) -> Tuple[DiagnosticBundle, bool]:
    """
    Возвращает диагностический пакет, при необходимости вызывая LLM.

    Returns:
        bundle, from_cache
    """

    cached = user_memory.get_diagnostic_bundle(user_id)
    if cached and not force:
        logger.info("Используем сохранённый диагностический пакет user_id=%s", user_id)
        return DiagnosticBundle.model_validate(cached), True

    bundle = run_diagnostic_agent(user_id)
    user_memory.upsert_diagnostic_bundle(user_id, bundle.model_dump(mode="json"))
    logger.info("Сохранён новый диагностический пакет user_id=%s", user_id)
    return bundle, False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Диагностический агент (демо).")
    parser.add_argument("--user-id", type=str, required=True)
    parser.add_argument("--as-json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    bundle = run_diagnostic_agent(UUID(args.user_id))
    payload = bundle.model_dump(mode="json")
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
