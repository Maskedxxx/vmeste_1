# app/services/week_plan_agent.py
# --- agent_meta ---
# role: week-plan-agent
# contract: подбирает материалы по тегам и строит план на 7 дней
# owner: backend-core
# last_reviewed: 2025-11-11
# interfaces:
#   - generate_week_plan(user_id: UUID, tags: list[str]) -> WeekPlan
# --- /agent_meta ---

"""Агент, создающий план на 7 дней на основе профиля и тегов проблем."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import UUID

from openai import OpenAI

from app.db.connection import fetch_all
from app.db.repositories import user_memory, users
from app.models import PlanItem, WeekPlan, UserProfileModel
from config import get_settings


logger = logging.getLogger("vmeste.services.week_plan_agent")

SYSTEM_PROMPT = (
    "Ты коуч-психолог платформы «Вместе». На основе профиля пользователя и списка доступных "
    "материалов составь подробный план на 7 дней. Каждый день должен ссылаться на конкретный "
    "контент (content_id) и описывать цель и краткую инструкцию. Можно повторять материалы, "
    "но с разным акцентом. Учти теги проблемы и стадии пользователя."
)


@dataclass
class ContentItem:
    content_id: str
    title: str
    summary: str
    topic: str | None
    content_type: str | None
    tags: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "title": self.title,
            "summary": self.summary,
            "topic": self.topic,
            "content_type": self.content_type,
            "tags": self.tags,
        }


def _load_profile(user_id: UUID) -> UserProfileModel:
    user = users.get_by_id(user_id)
    if user is None:
        raise LookupError(f"User {user_id} not found")
    try:
        return UserProfileModel.model_validate(user.profile_json or {})
    except Exception:
        logger.warning("profile_json повреждён, возвращаю пустой профиль")
        return UserProfileModel()


def _normalize_tags(tags: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    if not tags:
        return normalized
    for tag in tags:
        if not tag:
            continue
        value = str(tag).strip()
        if not value:
            continue
        normalized.append(value.lower())
    return normalized


def _fetch_catalog() -> list[ContentItem]:
    rows = fetch_all(
        """
        SELECT
            content_id,
            title,
            COALESCE(summary, description, '') AS summary,
            topic,
            content_type,
            tags
        FROM psychologist_content
        WHERE available = TRUE
          AND is_deleted = FALSE
        """
    )
    catalog: list[ContentItem] = []
    for row in rows:
        catalog.append(
            ContentItem(
                content_id=str(row["content_id"]),
                title=row["title"],
                summary=row["summary"] or "",
                topic=row.get("topic"),
                content_type=row.get("content_type"),
                tags=_normalize_tags(row.get("tags")),
            )
        )
    return catalog


def select_content_by_tags(tags: Sequence[str], limit: int = 12) -> list[ContentItem]:
    target = set(_normalize_tags(tags))
    catalog = _fetch_catalog()
    logger.info("Каталог материалов: %s записей, теги запроса: %s", len(catalog), list(target))
    scored: list[tuple[int, ContentItem]] = []

    for item in catalog:
        item_tags = set(item.tags)
        score = len(target & item_tags) if target else 1
        if score == 0 and target:
            continue
        scored.append((score, item))

    if not scored and catalog:
        scored = [(0, item) for item in catalog]

    scored.sort(key=lambda x: (-x[0], x[1].title))
    selected = [item for _, item in scored[:limit]]
    logger.info(
        "Подбор контента: выбрано %s материалов: %s",
        len(selected),
        [item.content_id for item in selected],
    )
    return selected


def _normalized_eq(a: Sequence[str], b: Sequence[str]) -> bool:
    return _normalize_tags(a) == _normalize_tags(b)


class WeekPlanAgent:
    """Инкапсулирует вызов OpenAI для построения плана."""

    def __init__(self, *, client: OpenAI | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._client = client or OpenAI()
        self._model = model_name or getattr(settings, "openai_model", "gpt-4.1-mini")

    def generate_plan(self, profile: UserProfileModel, materials: list[ContentItem]) -> WeekPlan:
        if not materials:
            raise RuntimeError("Нет материалов для построения плана")
        payload = {
            "profile": profile.model_dump(mode="json"),
            "materials": [item.to_payload() for item in materials],
            "instructions": (
                "Сформируй список ровно из 7 элементов. Каждый элемент должен использовать один "
                "из материалов из списка. Если материалов меньше 7, повторяй их, но меняй вклад "
                "и подход. В поле goal отрази, какую проблему решает день, а в instructions опиши, "
                "как выполнять задачу."
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
            temperature=0.3,
        )
        plan = completion.choices[0].message.parsed
        if plan is None:
            raise RuntimeError("LLM не вернула план")
        return plan


def generate_week_plan(user_id: UUID, tags: Sequence[str]) -> WeekPlan:
    profile = _load_profile(user_id)
    materials = select_content_by_tags(tags, limit=12)
    agent = WeekPlanAgent()
    logger.info("Запуск week plan agent для user_id=%s (материалов=%s)", user_id, len(materials))
    plan = agent.generate_plan(profile, materials)
    return plan


def run_week_plan_with_cache(
    user_id: UUID,
    tags: Sequence[str],
    *,
    force: bool = False,
) -> tuple[WeekPlan, bool]:
    """Возвращает недельный план, используя кэш при наличии."""

    normalized_tags = _normalize_tags(tags)
    if not normalized_tags:
        raise ValueError("Нужно указать хотя бы один тег для подбора контента")

    cached = user_memory.get_week_plan(user_id)
    if cached and not force:
        cached_tags = _normalize_tags(cached.get("tags"))
        if _normalized_eq(cached_tags, normalized_tags):
            logger.info("Используем сохранённый план user_id=%s", user_id)
            plan_payload = cached.get("plan")
            if not isinstance(plan_payload, dict):
                logger.warning("Сохранённый план повреждён, пересоздаём user_id=%s", user_id)
            else:
                return WeekPlan.model_validate(plan_payload), True

    plan = generate_week_plan(user_id, normalized_tags)
    payload = {
        "tags": normalized_tags,
        "plan": plan.model_dump(mode="json"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    user_memory.upsert_week_plan(user_id, payload)
    logger.info("Сохранён новый недельный план user_id=%s", user_id)
    return plan, False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Демо агента недельного плана.")
    parser.add_argument("--user-id", required=True, type=str)
    parser.add_argument("--tags", type=str, default="")
    parser.add_argument("--as-json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    plan = generate_week_plan(UUID(args.user_id), tags)
    payload = plan.model_dump(mode="json")
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in plan.days:
            print(f"День {item.day}: {item.title} ({item.content_id}) — {item.goal}")
