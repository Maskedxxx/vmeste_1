# app/services/week_plan_agent.py
# --- agent_meta ---
# role: week-plan-agent
# contract: строит 7-дневный план на основе профиля, квиза и диагностики
# owner: backend-core
# last_reviewed: 2025-11-19
# interfaces:
#   - run_week_plan_with_cache(user_id: UUID, tags: list[str] | None, force: bool)
# --- /agent_meta ---

"""Агент, создающий план на 7 дней на основе полного контекста пользователя."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from openai import OpenAI

from app.db.repositories import user_memory, users
from app.models import WeekPlan, UserProfileModel
from app.models.diagnostic import DiagnosticBundle
from config import get_settings


logger = logging.getLogger("vmeste.services.week_plan_agent")

SYSTEM_PROMPT = (
    "Ты коуч-психолог платформы «Вместе». На основе профиля пользователя, его квизовых ответов, "
    "выбранных тегов и результатов диагностики составь подробный, но простой план на 7 дней. "
    "Каждый день должен содержать одну практику или задачу, которую можно выполнить самостоятельно: "
    "дыхательные техники, ведение дневника, социальные шаги, мягкие физические упражнения, встречи "
    "с врачами и т.д. Избегай упоминаний платного контента и сложных инструментов."
)


def _load_profile(user_id: UUID) -> UserProfileModel:
    user = users.get_by_id(user_id)
    if user is None:
        raise LookupError(f"User {user_id} not found")
    try:
        return UserProfileModel.model_validate(user.profile_json or {})
    except Exception:
        logger.warning("profile_json повреждён, возвращаю пустой профиль")
        return UserProfileModel()


def _normalize_tags(tags: Sequence[str] | None) -> list[str]:
    normalized: list[str] = []
    if not tags:
        return normalized
    for tag in tags:
        if not tag:
            continue
        value = str(tag).strip().lower()
        if not value or value in normalized:
            continue
        normalized.append(value)
    return normalized


def _gather_diagnostic_tags(bundle: DiagnosticBundle | None) -> list[str]:
    if bundle is None:
        return []
    tags: list[str] = []
    for block in (bundle.body, bundle.mind, bundle.sex):
        for tag in block.tags:
            normalized = tag.strip().lower()
            if normalized and normalized not in tags:
                tags.append(normalized)
    return tags


def _build_context_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class WeekPlanAgent:
    """Инкапсулирует вызов OpenAI для построения плана."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate_plan(
        self,
        *,
        profile: UserProfileModel,
        quiz_payload: dict[str, Any] | None,
        diagnostic: DiagnosticBundle,
        focus_tags: Sequence[str],
    ) -> WeekPlan:
        payload = {
            "profile": profile.model_dump(mode="json"),
            "quiz_profile": quiz_payload,
            "diagnostic": diagnostic.model_dump(mode="json"),
            "focus_tags": list(focus_tags),
            "instructions": (
                "Сформируй 7 последовательных дней. Для каждого дня задай: title, goal, instructions, tags, focus_area. "
                "Через неделю пользователь должен почувствовать облегчение по ключевым симптомам."
            ),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        completion = self._client.chat.completions.parse(
            model=self._model,
            messages=messages,
            response_format=WeekPlan,
            temperature=0.35,
        )
        plan = completion.choices[0].message.parsed
        if plan is None:
            raise RuntimeError("LLM не вернула план")
        return plan


def run_week_plan_with_cache(
    user_id: UUID,
    tags: Sequence[str] | None = None,
    *,
    force: bool = False,
) -> tuple[WeekPlan, bool, list[str]]:
    """Возвращает недельный план, используя кэш при наличии."""

    profile = _load_profile(user_id)
    quiz_profile = user_memory.get_quiz_profile(user_id)
    diagnostic_raw = user_memory.get_diagnostic_bundle(user_id)
    if diagnostic_raw is None:
        raise ValueError("Диагностика ещё не выполнена")
    diagnostic = DiagnosticBundle.model_validate(diagnostic_raw)

    normalized_tags = _normalize_tags(tags)
    derived_tags = normalized_tags or _gather_diagnostic_tags(diagnostic)
    if not derived_tags and profile.recommended_focus:
        derived_tags = _normalize_tags(profile.recommended_focus)

    quiz_payload = quiz_profile.model_dump(mode="json") if quiz_profile else None
    context_payload = {
        "profile": profile.model_dump(mode="json"),
        "quiz": quiz_payload,
        "diagnostic": diagnostic.model_dump(mode="json"),
        "tags": derived_tags,
    }
    context_hash = _build_context_hash(context_payload)

    cached = user_memory.get_week_plan(user_id)
    if cached and not force and cached.get("context_hash") == context_hash:
        plan_payload = cached.get("plan")
        if isinstance(plan_payload, dict):
            logger.info("Возвращаем недельный план из кэша user_id=%s", user_id)
            return WeekPlan.model_validate(plan_payload), True, list(cached.get("tags", []))
        logger.warning("Повреждённый кэш плана user_id=%s, пересоздаём", user_id)

    agent = WeekPlanAgent()
    plan = agent.generate_plan(
        profile=profile,
        quiz_payload=quiz_payload,
        diagnostic=diagnostic,
        focus_tags=derived_tags,
    )

    payload = {
        "tags": derived_tags,
        "plan": plan.model_dump(mode="json"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context_hash": context_hash,
    }
    user_memory.upsert_week_plan(user_id, payload)
    logger.info("Сохранён новый недельный план user_id=%s", user_id)
    return plan, False, derived_tags


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Демо агента недельного плана.")
    parser.add_argument("--user-id", required=True, type=str)
    parser.add_argument("--tags", type=str, default="")
    parser.add_argument("--as-json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    plan, _ = run_week_plan_with_cache(UUID(args.user_id), tags)
    payload = plan.model_dump(mode="json")
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in plan.days:
            print(f"День {item.day}: {item.title} — {item.goal}")
