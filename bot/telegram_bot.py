# bot/telegram_bot.py
# --- agent_meta ---
# role: telegram-entry-bot
# contract: Telegram-бот для тестирования пайплайна входа (entry) через /entry API
# owner: backend-core
# last_reviewed: 2025-11-19
# interfaces:
#   - main() -> None
# --- /agent_meta ---

"""Простой Telegram-бот на aiogram, который проверяет пользователя через /entry API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from pydantic import EmailStr, TypeAdapter, ValidationError

from config import get_settings


logger = logging.getLogger("vmeste.telegram_bot")
EMAIL_ADAPTER = TypeAdapter(EmailStr)
QUIZ_START_CALLBACK = "quiz_start"
STATUS_CALLBACK = "status_show"
DIAGNOSTIC_CALLBACK = "diagnostic_start"
DIAGNOSTIC_TAG_PREFIX = "diag_tag:"
DIAGNOSTIC_NEXT_CALLBACK = "diagnostic_next"
DIAGNOSTIC_BLOCK_TITLES = {
    "body": "Тело",
    "mind": "Психика",
    "sex": "Сексология",
}
DIAGNOSTIC_BLOCK_ORDER = ["body", "mind", "sex"]
WEEK_PLAN_CALLBACK = "week_plan_start"


class EntryFlow(StatesGroup):
    """Состояния диалога входа."""

    waiting_for_email = State()
    ready = State()
    quiz_active = State()
    diagnostic_active = State()


def _setup_logging() -> None:
    """Глобальные настройки логирования для бота."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
    )


def _api_entry_request(email: str) -> dict[str, Any]:
    """Делает POST /entry и возвращает json."""

    settings = get_settings()
    base_url = settings.api_base_url.rstrip("/")
    url = f"{base_url}/entry"
    logger.info("Вызываю API /entry для %s", email)
    response = requests.post(url, json={"email": email}, timeout=10)
    if response.status_code >= 400:
        logger.error("API /entry вернуло %s: %s", response.status_code, response.text)
        raise RuntimeError("Сервис вернул ошибку, попробуйте позже.")
    return response.json()


def _api_fetch_quiz_questions() -> list[dict[str, Any]]:
    """Возвращает список вопросов квиза через GET /quiz/questions."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/quiz/questions"
    logger.info("Запрашиваю список вопросов квиза")
    response = requests.get(url, timeout=10)
    if response.status_code >= 400:
        logger.error("Ошибка при получении вопросов квиза: %s", response.text)
        raise RuntimeError("Не удалось загрузить вопросы квиза.")
    return response.json()


def _api_submit_quiz_answers(user_id: str, answers: list[dict[str, str]]) -> dict[str, Any]:
    """Отправляет ответы пользователя в /quiz/submit и возвращает JSON-ответ."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/quiz/submit"
    payload = {"user_id": user_id, "answers": answers}
    logger.info("Отправляю %s ответов квиза для user_id=%s", len(answers), user_id)
    response = requests.post(url, json=payload, timeout=15)
    if response.status_code >= 400:
        logger.error("Не удалось сохранить квиз: %s", response.text)
        raise RuntimeError("API не приняло ответы квиза.")
    return response.json()


def _api_enrich_profile(user_id: str) -> dict[str, Any]:
    """Запускает обогащение профиля пользователя."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/users/{user_id}/profile/enrich"
    logger.info("Запуск обогащения профиля user_id=%s", user_id)
    response = requests.post(url, json={"force": False}, timeout=30)
    if response.status_code >= 400:
        logger.error("Профиль не обогатился: %s", response.text)
        raise RuntimeError("Не удалось обновить профиль.")
    return response.json()


def _api_get_user(user_id: str) -> dict[str, Any]:
    """Возвращает карточку пользователя."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/users/{user_id}"
    response = requests.get(url, timeout=10)
    if response.status_code >= 400:
        raise RuntimeError("Не удалось прочитать пользователя")
    return response.json()


def _api_run_diagnostic(user_id: str) -> dict[str, Any]:
    """Запускает диагностический агент."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/users/{user_id}/diagnostic/run"
    response = requests.post(url, json={"force": False}, timeout=60)
    if response.status_code >= 400:
        logger.error("Диагностика недоступна: %s", response.text)
        raise RuntimeError("Не удалось запустить диагностику.")
    return response.json()


def _api_run_week_plan(user_id: str, selected_tags: list[str]) -> dict[str, Any]:
    """Запускает генерацию недельного плана."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/users/{user_id}/week-plan/run"
    payload: dict[str, Any] = {"force": False}
    if selected_tags:
        payload["selected_tags"] = selected_tags
    response = requests.post(url, json=payload, timeout=60)
    if response.status_code >= 400:
        logger.error("Неделя не построена: %s", response.text)
        raise RuntimeError("Не удалось построить план.")
    return response.json()


def _api_get_memory(user_id: str) -> dict[str, Any] | None:
    """Возвращает память пользователя."""

    settings = get_settings()
    url = f"{settings.api_base_url.rstrip('/')}/users/{user_id}/memory"
    response = requests.get(url, timeout=10)
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        logger.warning("Не удалось получить память пользователя: %s", response.text)
        return None
    return response.json()


def _build_ready_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с действиями пользователя."""

    quiz_button = InlineKeyboardButton(text="Пройти квиз", callback_data=QUIZ_START_CALLBACK)
    diagnostic_button = InlineKeyboardButton(text="Диагностика", callback_data=DIAGNOSTIC_CALLBACK)
    week_plan_button = InlineKeyboardButton(text="План на 7 дней", callback_data=WEEK_PLAN_CALLBACK)
    status_button = InlineKeyboardButton(text="Статус", callback_data=STATUS_CALLBACK)
    return InlineKeyboardMarkup(
        inline_keyboard=[[quiz_button], [diagnostic_button], [week_plan_button], [status_button]]
    )


def _format_question_text(question: dict[str, Any], index: int, total: int) -> str:
    """Собирает текст вопроса с учетом подсказок и вариантов."""

    lines = [f"Вопрос {index + 1}/{total}", question.get("text", "")]
    helper = question.get("helper")
    if helper:
        lines.append(f"Подсказка: {helper}")
    options = question.get("options") or []
    if options:
        option_lines = [f"- {opt.get('label')} ({opt.get('value')})" for opt in options]
        lines.append("Варианты:\n" + "\n".join(option_lines))
    return "\n".join(lines)


async def _send_quiz_question(message: Message | None, question: dict[str, Any], index: int, total: int) -> None:
    """Отправляет очередной вопрос пользователю."""

    if message is None:
        return
    await message.answer(_format_question_text(question, index, total), disable_notification=True)


WELCOME_MESSAGE = """🌿 ВМЕСТЕ Bot

Персональный wellness-помощник для комплексного анализа здоровья и построения индивидуального плана развития.

📋 Начало работы:

/start — Начать работу с ботом
Введите email для регистрации или входа в систему.

🎯 Основные функции:

Пройти квиз — Создать свой профиль
Ответьте на вопросы о себе, чтобы система могла составить персональные рекомендации.

Диагностика — Комплексный анализ
Получите детальный анализ по трём направлениям:
• Тело — физическое здоровье
• Психика — ментальное состояние
• Сексология — интимное здоровье

Для каждого направления вы получите:
— Персональный анализ
— Рекомендации врачей
— Список анализов
— Подобранный контент

Выбор тегов — Приоритеты для плана
После каждого блока диагностики выберите теги — темы, которые для вас наиболее актуальны. На основе выбранных тегов система построит персональный недельный план с фокусом именно на ваших приоритетах.

План на 7 дней — Ваш недельный план
Получите пошаговый план действий на неделю с конкретными целями и инструкциями на каждый день, построенный на основе выбранных вами тегов.

Статус — Посмотреть свой профиль
Просмотрите текущий прогресс, выбранные теги и рекомендации.

🚀 Порядок работы:

1. Введите email после /start
2. Пройдите квиз для создания профиля
3. Запустите диагностику
4. Выберите важные для вас теги в каждом блоке
5. Получите персональный план на 7 дней
"""


async def handle_start(message: Message, state: FSMContext) -> None:
    """Приветствие и запрос email."""

    await state.clear()
    await state.set_state(EntryFlow.waiting_for_email)
    await message.answer(WELCOME_MESSAGE)
    await message.answer("Для начала отправьте мне свой email:")


async def handle_email(message: Message, state: FSMContext) -> None:
    """Обрабатывает введённый email и вызывает /entry."""

    email_raw = (message.text or "").strip()
    try:
        email_valid = str(EMAIL_ADAPTER.validate_python(email_raw)).lower()
    except (ValidationError, ValueError):
        await message.answer("Кажется, это не похоже на email. Попробуйте ещё раз (пример: demo@vmeste.io).")
        return

    try:
        data = _api_entry_request(email_valid)
    except Exception as error:
        logger.exception("Ошибка при вызове /entry: %s", error)
        await message.answer("Не удалось связаться с API, повторите попытку позже.")
        return

    user_info = data.get("user", {})
    is_new = data.get("is_new")
    quiz_completed = data.get("quiz_completed")
    reply_lines = [
        f"Email: {email_valid}",
        f"Новый пользователь: {'да' if is_new else 'нет'}",
        f"Квиз завершён: {'да' if quiz_completed else 'нет'}",
        f"User ID: {user_info.get('user_id', 'неизвестно')}",
    ]
    memory = None
    memory_data: dict[str, Any] = {}
    try:
        memory = _api_get_memory(str(user_info.get("user_id", "")))
        memory_data = (memory or {}).get("memory_data") or {}
    except Exception as error:
        logger.warning("Не удалось получить память пользователя: %s", error)
    diagnostic_done = bool(memory_data.get("diagnostic_bundle"))
    week_plan_info = memory_data.get("week_plan") or {}
    week_plan_ready = bool(week_plan_info.get("plan"))
    await state.update_data(
        user_id=str(user_info.get("user_id", "")),
        email=email_valid,
        quiz_completed=bool(quiz_completed),
        profile_enriched=bool(user_info.get("profile_json")),
        diagnostic_done=diagnostic_done,
        diagnostic_results=[],
        week_plan_ready=week_plan_ready,
        week_plan_data=week_plan_info.get("plan"),
        week_plan_tags=week_plan_info.get("tags") or [],
    )
    await state.set_state(EntryFlow.ready)
    await message.answer(
        "\n".join(reply_lines),
        reply_markup=_build_ready_keyboard(),
    )


async def handle_fallback(message: Message, state: FSMContext) -> None:
    """Ответ на произвольные тексты вне сценария."""

    current_state = await state.get_state()
    if current_state == EntryFlow.ready.state:
        await message.answer("Нажмите кнопку «Пройти квиз» или отправьте /start, чтобы ввести email заново.")
        return
    await message.answer("Отправьте /start и далее введите email, чтобы проверить статус профиля.")


async def handle_quiz_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает прохождение квиза по нажатию кнопки."""

    data = await state.get_data()
    user_id: str | None = data.get("user_id")
    if data.get("quiz_completed"):
        await callback.answer("Квиз уже пройден.", show_alert=True)
        if callback.message:
            await callback.message.answer("Квиз уже пройден. Посмотрите статус или запустите диагностику.")
        return
    if not user_id:
        await callback.answer("Сначала отправьте email.", show_alert=True)
        return
    try:
        questions = _api_fetch_quiz_questions()
    except RuntimeError as error:
        await callback.answer("Не удалось загрузить вопросы.", show_alert=True)
        logger.error("Квиз недоступен: %s", error)
        return
    if not questions:
        await callback.answer("Вопросы квиза не найдены.", show_alert=True)
        return
    await state.update_data(
        quiz_questions=questions,
        quiz_answers=[],
        quiz_index=0,
    )
    await state.set_state(EntryFlow.quiz_active)
    await callback.answer()
    await _send_quiz_question(callback.message, questions[0], 0, len(questions))


async def handle_status(callback: CallbackQuery, state: FSMContext) -> None:
    """Отправляет пользователю текущий статус квиза и профиля."""

    data = await state.get_data()
    user_id: str | None = data.get("user_id")
    if not user_id:
        await callback.answer("Сначала отправьте email.", show_alert=True)
        return
    try:
        user = _api_get_user(user_id)
    except RuntimeError:
        await callback.answer("Не удалось получить статус.", show_alert=True)
        return
    profile_json = user.get("profile_json") or {}
    quiz_completed = data.get("quiz_completed")
    profile_enriched = bool(profile_json)
    await state.update_data(profile_enriched=profile_enriched)
    diagnostic_done = data.get("diagnostic_done", False)
    diagnostic_results = data.get("diagnostic_results") or []
    diagnostic_recs: dict[str, Any] = data.get("diagnostic_recommendations") or {}
    week_plan_ready = data.get("week_plan_ready", False)
    week_plan_data = data.get("week_plan_data") or {}
    week_plan_tags = data.get("week_plan_tags") or []
    lines = [
        f"User ID: {user_id}",
        f"Квиз завершён: {'да' if quiz_completed else 'нет'}",
        f"Профиль обогащён: {'да' if profile_enriched else 'нет'}",
        f"Диагностика выполнена: {'да' if diagnostic_done else 'нет'}",
        f"План на 7 дней: {'готов' if week_plan_ready else 'нет'}",
    ]
    if diagnostic_done and diagnostic_results:
        lines.append("Выбранные теги:")
        for result in diagnostic_results:
            title = result.get("title", "Блок")
            tags = result.get("tags") or []
            tag_text = ", ".join(tags) if tags else "теги не выбраны"
            lines.append(f"- {title}: {tag_text}")
    if diagnostic_recs:
        lines.append("Контент от агента:")
        for block_code in DIAGNOSTIC_BLOCK_ORDER:
            rec = diagnostic_recs.get(block_code)
            if not rec:
                continue
            title = DIAGNOSTIC_BLOCK_TITLES.get(block_code, block_code.title())
            content = rec.get("content") or {}
            price = content.get("price")
            price_part = f" — {price}" if price else ""
            lines.append(f"- {title}: {content.get('title', 'без названия')}{price_part}")
    if week_plan_ready and week_plan_data:
        preview_days = []
        for day in (week_plan_data.get("days") or [])[:2]:
            preview_days.append(f"День {day.get('day')}: {day.get('title')}")
        if preview_days:
            lines.append("Первые шаги плана:\n- " + "\n- ".join(preview_days))
        if week_plan_tags:
            lines.append("Теги плана: " + ", ".join(week_plan_tags[:6]))
    await callback.answer()
    await callback.message.answer("\n".join(lines))


async def handle_quiz_answer(message: Message, state: FSMContext) -> None:
    """Обрабатывает ответы на вопросы и отправляет результат на API."""

    data = await state.get_data()
    questions: list[dict[str, Any]] = data.get("quiz_questions") or []
    index: int = data.get("quiz_index", 0)
    answers: list[dict[str, str]] = data.get("quiz_answers") or []
    user_id: str | None = data.get("user_id")
    if not questions or user_id is None:
        await message.answer("Сначала введите email и нажмите «Пройти квиз».")
        await state.set_state(EntryFlow.waiting_for_email)
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Ответ не должен быть пустым. Попробуйте еще раз.")
        return
    current_question = questions[index]
    answers.append({"question_id": current_question.get("question_id", ""), "value": text})
    index += 1
    if index >= len(questions):
        try:
            submit_result = _api_submit_quiz_answers(user_id, answers)
        except RuntimeError as error:
            await message.answer("Не удалось сохранить ответы, попробуйте позже.")
            logger.error("Ошибка отправки квиза: %s", error)
            await state.set_state(EntryFlow.ready)
            return
        await message.answer(
            "Квиз завершён. "
            f"Версия: {submit_result.get('version', 'не указана')}. "
            f"Ответов сохранено: {len(answers)}",
        )
        await state.update_data(
            quiz_questions=None,
            quiz_answers=None,
            quiz_index=0,
            quiz_completed=True,
        )
        await _auto_enrich_profile_if_needed(message, state, user_id)
        await state.set_state(EntryFlow.ready)
        await message.answer(
            "Можете повторно пройти квиз позже или посмотреть статус.",
            reply_markup=_build_ready_keyboard(),
        )
        return
    await state.update_data(quiz_answers=answers, quiz_index=index)
    await _send_quiz_question(message, questions[index], index, len(questions))


async def handle_diagnostic_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает сценарий диагностики."""

    data = await state.get_data()
    user_id: str | None = data.get("user_id")
    quiz_completed = data.get("quiz_completed")
    profile_enriched = data.get("profile_enriched")
    diagnostic_done = data.get("diagnostic_done")
    if not user_id:
        await callback.answer("Сначала отправьте email.", show_alert=True)
        return
    if not quiz_completed:
        await callback.answer("Сначала завершите квиз.", show_alert=True)
        return
    if not profile_enriched:
        await callback.answer("Сначала дождитесь обогащения профиля.", show_alert=True)
        return
    if diagnostic_done:
        await callback.answer("Диагностика уже выполнена.", show_alert=True)
        if callback.message:
            await callback.message.answer("Диагностика уже выполнена. Посмотрите статус.")
        return
    await callback.answer("Запускаю диагностику...", show_alert=False)
    if callback.message:
        await callback.message.answer("Диагностика запускается через AI, подождите до 1 минуты...")
    try:
        diagnostic_response = _api_run_diagnostic(user_id)
    except RuntimeError:
        await callback.answer("Диагностика временно недоступна.", show_alert=True)
        return
    bundle = diagnostic_response.get("bundle") or {}
    recommendations = diagnostic_response.get("recommendations") or []
    rec_map = {rec.get("block"): rec for rec in recommendations}
    blocks = [
        {"title": DIAGNOSTIC_BLOCK_TITLES.get(code, code.title()), "code": code, "data": bundle.get(code)}
        for code in DIAGNOSTIC_BLOCK_ORDER
    ]
    await state.update_data(
        diagnostic_blocks=blocks,
        diagnostic_index=0,
        diagnostic_results=[],
        diagnostic_current_selected=[],
        diagnostic_done=False,
        diagnostic_recommendations=rec_map,
    )
    await state.set_state(EntryFlow.diagnostic_active)
    await _send_diagnostic_block(callback.message, state)


async def _send_diagnostic_block(message: Message | None, state: FSMContext) -> None:
    """Отправляет пользователю текущий блок диагностики."""

    if message is None:
        return
    data = await state.get_data()
    blocks: list[dict[str, Any]] = data.get("diagnostic_blocks") or []
    index: int = data.get("diagnostic_index", 0)
    if index >= len(blocks):
        await message.answer("Диагностика завершена.")
        await state.set_state(EntryFlow.ready)
        await message.answer("Возвращаемся в главное меню.", reply_markup=_build_ready_keyboard())
        return
    block = blocks[index]
    block_data = block.get("data") or {}
    title = block.get("title", f"Блок {index + 1}")
    block_code = block.get("code")
    analysis = block_data.get("analysis", "Нет анализа.")
    tags = block_data.get("tags") or []
    if not tags:
        tags = ["нет-тегов"]
    # Ограничиваем до 5 тегов для удобства бота/LLM
    tags = tags[:5]
    tag_map = {f"t{i}": tag for i, tag in enumerate(tags)}
    doctors = block_data.get("recommended_doctors") or []
    tests = block_data.get("recommended_tests") or []
    lines = [f"{title}", analysis]
    if doctors:
        lines.append("Рекомендуемые врачи:\n- " + "\n- ".join(doctors))
    if tests:
        lines.append("Рекомендуемые анализы:\n- " + "\n- ".join(tests))
    lines.append("Выберите подходящие теги:")
    await state.update_data(
        diagnostic_current_tag_map=tag_map,
        diagnostic_current_title=title,
        diagnostic_current_code=block_code,
        diagnostic_current_selected=[],
    )
    await message.answer(
        "\n\n".join(lines),
        reply_markup=_build_tag_keyboard(tag_map),
        disable_notification=True,
    )
    await _send_block_recommendation(message, block_code, title, state)


def _build_tag_keyboard(tag_map: dict[str, str]) -> InlineKeyboardMarkup:
    """Создаёт клавиатуру с тегами и кнопкой 'Далее'."""

    buttons: list[list[InlineKeyboardButton]] = []
    for tag_id, tag_value in tag_map.items():
        buttons.append(
            [InlineKeyboardButton(text=tag_value, callback_data=f"{DIAGNOSTIC_TAG_PREFIX}{tag_id}")]
        )
    buttons.append([InlineKeyboardButton(text="Далее", callback_data=DIAGNOSTIC_NEXT_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _send_block_recommendation(
    message: Message | None,
    block_code: str | None,
    block_title: str,
    state: FSMContext,
) -> None:
    """Выводит карточку контента после блока диагностики."""

    if message is None or not block_code:
        return
    data = await state.get_data()
    rec_map: dict[str, Any] = data.get("diagnostic_recommendations") or {}
    block_rec = rec_map.get(block_code)
    if not block_rec:
        return
    recommendation = block_rec.get("recommendation") or {}
    content = block_rec.get("content") or {}
    offer = recommendation.get("offer") or {}
    content_title = content.get("title", "Материал")
    content_type = content.get("content_type")
    price = content.get("price")
    summary = content.get("summary")
    tags = content.get("tags") or []
    media_hint = content.get("media_hint") or content.get("metadata_note")
    lines = [f"Контент для блока «{block_title}».", recommendation.get("message", "Подбор еще формируется.")]
    lines.append(f"Материал: {content_title}{f' ({content_type})' if content_type else ''}")
    if summary:
        lines.append(summary)
    if price:
        lines.append(f"Стоимость: {price}")
    if media_hint:
        lines.append(str(media_hint))
    if tags:
        tag_text = ", ".join(str(tag) for tag in tags[:5])
        lines.append("Теги: " + tag_text)
    why = offer.get("why")
    if why:
        lines.append(f"Почему важно: {why}")
    expected = offer.get("expected_result")
    if expected:
        lines.append(f"Результат: {expected}")
    cta = offer.get("cta")
    if cta:
        lines.append(f"Действие: {cta}")
    follow_up = recommendation.get("follow_up_question")
    if follow_up:
        lines.append(f"Вопрос для вас: {follow_up}")
    buttons: list[list[InlineKeyboardButton]] = []
    url = content.get("url")
    if url:
        buttons.append([InlineKeyboardButton(text="Перейти к материалу", url=url)])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n\n".join(lines), reply_markup=markup, disable_web_page_preview=True)


async def handle_diagnostic_tag(callback: CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает выбор тега пользователем."""

    data = await state.get_data()
    tag_id = callback.data.removeprefix(DIAGNOSTIC_TAG_PREFIX)
    selected: list[str] = data.get("diagnostic_current_selected") or []
    current_map: dict[str, str] = data.get("diagnostic_current_tag_map") or {}
    tag_value = current_map.get(tag_id)
    if tag_value is None:
        await callback.answer("Тег недоступен.", show_alert=False)
        return
    if tag_value in selected:
        await callback.answer("Тег уже выбран.", show_alert=False)
        return
    selected.append(tag_value)
    current_map.pop(tag_id, None)
    await state.update_data(
        diagnostic_current_selected=selected,
        diagnostic_current_tag_map=current_map,
    )
    await callback.answer(f"Выбрано: {tag_value}")
    await callback.message.edit_reply_markup(reply_markup=_build_tag_keyboard(current_map))
    await callback.message.answer(f"Тег «{tag_value}» добавлен.")


async def handle_diagnostic_next(callback: CallbackQuery, state: FSMContext) -> None:
    """Переходит к следующему блоку диагностики или завершает сценарий."""

    await _persist_current_block_result(state)
    data = await state.get_data()
    index: int = data.get("diagnostic_index", 0) + 1
    blocks: list[dict[str, Any]] = data.get("diagnostic_blocks") or []
    if index >= len(blocks):
        await callback.answer()
        await _finish_diagnostic(callback.message, state)
        return
    await state.update_data(diagnostic_index=index)
    await callback.answer()
    await _send_diagnostic_block(callback.message, state)


async def _finish_diagnostic(message: Message | None, state: FSMContext) -> None:
    """Завершает сценарий диагностики, выводя сводку тегов."""

    if message is None:
        return
    data = await state.get_data()
    results: list[dict[str, Any]] = data.get("diagnostic_results") or []
    lines = ["Диагностика завершена."]
    if results:
        for result in results:
            title = result.get("title", "Блок")
            tags = result.get("tags") or []
            tag_text = ", ".join(tags) if tags else "теги не выбраны"
            lines.append(f"- {title}: {tag_text}")
    else:
        lines.append("Вы не выбрали теги для блоков.")
    await state.update_data(
        diagnostic_done=True,
        diagnostic_blocks=None,
        diagnostic_index=0,
        diagnostic_current_tag_map={},
        diagnostic_current_title=None,
        diagnostic_current_selected=[],
        week_plan_ready=False,
        week_plan_data=None,
        week_plan_tags=[],
    )
    await state.set_state(EntryFlow.ready)
    await message.answer("\n".join(lines), reply_markup=_build_ready_keyboard())
    await _offer_week_plan(message)


async def _persist_current_block_result(state: FSMContext) -> None:
    """Сохраняет выбранные теги текущего блока в общий список."""

    data = await state.get_data()
    title = data.get("diagnostic_current_title")
    if title is None:
        return
    selected = list(data.get("diagnostic_current_selected") or [])
    results: list[dict[str, Any]] = data.get("diagnostic_results") or []
    if results and results[-1].get("title") == title:
        results[-1]["tags"] = selected
    else:
        results.append({"title": title, "tags": selected})
    await state.update_data(diagnostic_results=results)


async def _offer_week_plan(message: Message | None) -> None:
    """Предлагает построить недельный план после диагностики."""

    if message is None:
        return
    plan_button = InlineKeyboardButton(text="План на 7 дней", callback_data=WEEK_PLAN_CALLBACK)
    await message.answer(
        "Могу построить персональный план на 7 дней. Нажмите кнопку, когда будете готовы.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[plan_button]]),
    )


async def _send_week_plan_summary(
    message: Message | None,
    plan_payload: dict[str, Any] | None,
    tags: list[str] | None,
) -> None:
    """Отправляет пользователю готовый недельный план."""

    if message is None:
        return
    plan = plan_payload or {}
    days = plan.get("days") or []
    if not days:
        await message.answer("План пока пуст, попробуйте повторить запрос позже.")
        return
    lines = ["План на 7 дней готов."]
    if tags:
        lines.append("Теги фокуса: " + ", ".join(tags[:6]))
    for day in days:
        day_num = day.get("day")
        title = day.get("title") or "Без названия"
        goal = day.get("goal") or ""
        instructions = day.get("instructions") or ""
        focus_area = day.get("focus_area")
        day_lines = [f"День {day_num}: {title}"]
        if focus_area:
            day_lines.append(f"Фокус: {focus_area}")
        if goal:
            day_lines.append(f"Цель: {goal}")
        if instructions:
            day_lines.append(f"Шаги: {instructions}")
        day_tags = day.get("tags") or []
        if day_tags:
            day_lines.append("Теги: " + ", ".join(day_tags[:4]))
        lines.append("\n".join(day_lines))
    await message.answer("\n\n".join(lines), reply_markup=_build_ready_keyboard())


async def handle_week_plan_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Запускает построение или показ недельного плана."""

    data = await state.get_data()
    user_id: str | None = data.get("user_id")
    if not user_id:
        await callback.answer("Сначала отправьте email.", show_alert=True)
        return
    if not data.get("diagnostic_done"):
        await callback.answer("Сначала завершите диагностику.", show_alert=True)
        return
    if data.get("week_plan_ready"):
        await callback.answer("План уже готов.", show_alert=False)
        await _send_week_plan_summary(callback.message, data.get("week_plan_data"), data.get("week_plan_tags"))
        return

    tags: list[str] = []
    for result in data.get("diagnostic_results") or []:
        tags.extend(result.get("tags") or [])

    await callback.answer("Готовлю план...", show_alert=False)
    if callback.message:
        await callback.message.answer("AI готовит персональный план на 7 дней, подождите до 1 минуты...")
    try:
        response = _api_run_week_plan(user_id, tags)
    except RuntimeError:
        await callback.answer("План недоступен, попробуйте позже.", show_alert=True)
        return

    plan_payload = response.get("plan") or {}
    used_tags = response.get("tags") or []
    await state.update_data(
        week_plan_ready=True,
        week_plan_data=plan_payload,
        week_plan_tags=used_tags,
    )
    await _send_week_plan_summary(callback.message, plan_payload, used_tags)


async def _auto_enrich_profile_if_needed(message: Message, state: FSMContext, user_id: str) -> None:
    """Проверяет, обогащен ли профиль, и запускает обогащение при необходимости."""

    data = await state.get_data()
    if data.get("profile_enriched"):
        return
    try:
        response = _api_enrich_profile(user_id)
    except RuntimeError as error:
        await message.answer("Профиль пока не удалось обогатить. Попробуйте позже.")
        logger.error("Auto profile enrichment failed: %s", error)
        return
    await state.update_data(profile_enriched=True)
    enriched = response.get("enriched")
    await message.answer("Профиль обновлён." if enriched else "Профиль был актуальным, изменений не потребовалось.")


def build_dispatcher() -> Dispatcher:
    """Создаёт и настраивает Dispatcher с роутерами."""

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.register(handle_start, CommandStart())
    dispatcher.message.register(handle_email, EntryFlow.waiting_for_email, F.text)
    dispatcher.callback_query.register(handle_quiz_start, F.data == QUIZ_START_CALLBACK)
    dispatcher.callback_query.register(handle_status, F.data == STATUS_CALLBACK)
    dispatcher.callback_query.register(handle_diagnostic_start, F.data == DIAGNOSTIC_CALLBACK)
    dispatcher.callback_query.register(handle_diagnostic_next, F.data == DIAGNOSTIC_NEXT_CALLBACK)
    dispatcher.callback_query.register(handle_week_plan_start, F.data == WEEK_PLAN_CALLBACK)
    dispatcher.callback_query.register(
        handle_diagnostic_tag,
        F.data.startswith(DIAGNOSTIC_TAG_PREFIX),
    )
    dispatcher.message.register(handle_quiz_answer, EntryFlow.quiz_active, F.text)
    dispatcher.message.register(handle_fallback)
    return dispatcher


async def main() -> None:
    """Точка входа для запуска бота."""

    _setup_logging()
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в окружении или .env")

    bot = Bot(token=token, parse_mode=None)
    dispatcher = build_dispatcher()
    logger.info("Запуск Telegram-бота")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
