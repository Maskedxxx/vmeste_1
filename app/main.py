"""Точка входа FastAPI-приложения для проекта «Вместе» (v0)."""

from datetime import datetime, timezone
import logging
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.db.models import (
    ChatMessage,
    ChatMessageCreate,
    QuizProfile,
    QuizProfileUpdate,
    Session,
    SessionCreate,
    User,
    UserCreate,
    UserMemory,
    UserMemoryUpsert,
)
from app.db.repositories import chat_history, sessions, user_memory, users
from app.models.diagnostic import DiagnosticBundle
from app.models.quiz import QuizAnswer as QuizAnswerModel, QuizQuestion
from app.services.diagnostic_agent import run_diagnostic_with_cache
from app.services.profile_enrichment import EnsureProfileResult, ensure_profile_for_user
from app.services.quiz_service import DEFAULT_QUIZ_VERSION, get_quiz_questions, run_quiz_for_user, validate_answers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
)
logger = logging.getLogger("vmeste.api")

app = FastAPI(title="Vmeste API", version="0.3.0")


class HealthResponse(BaseModel):
    """Ответ сервиса на проверку работоспособности."""

    status: Literal["ok"]


class CloseSessionRequest(BaseModel):
    """Параметры закрытия сессии."""

    status: str = Field(..., min_length=1)
    ended_at: datetime | None = None


class UpdateStateRequest(BaseModel):
    """Новый стейт для сессии."""

    state_json: dict[str, object] = Field(default_factory=dict)


class ChatMessageRequest(BaseModel):
    """Запрос на добавление сообщения в сессию."""

    user_id: UUID
    sender: Literal["user", "assistant"]
    message_type: str = "text"
    payload: dict[str, object]
    request_timestamp: datetime | None = None
    response_timestamp: datetime | None = None
    conversion_completed: bool = False
    expert_score: int | None = Field(default=None, ge=1, le=5)
    user_score: int | None = Field(default=None, ge=1, le=5)


class MemoryRequest(BaseModel):
    """Запрос на обновление памяти пользователя."""

    memory_data: dict[str, object]


class ProfileRequest(BaseModel):
    """Запрос на обновление профиля пользователя."""

    profile_json: dict[str, object]


class ProfileEnrichmentRequest(BaseModel):
    """Параметры запуска обогащения профиля."""

    force: bool = False
    extra_context: str | None = None


class ProfileEnrichmentResponse(BaseModel):
    """Результат запуска обогащения профиля."""

    enriched: bool
    profile: dict[str, object]


class QuizAnswerRequest(BaseModel):
    """Ответ пользователя на вопрос квиза."""

    question_id: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class QuizSubmitRequest(BaseModel):
    """Пакет ответов квиза для сохранения через API."""

    user_id: UUID
    answers: list[QuizAnswerRequest]
    force: bool = False
    version: str | None = None


class QuizSubmitResponse(BaseModel):
    """Результат сохранения квиза."""

    was_updated: bool
    completed: bool
    version: str | None
    completed_at: datetime | None
    answers: dict[str, str]


class DiagnosticRequest(BaseModel):
    """Параметры запуска диагностического агента."""

    force: bool = False


class DiagnosticResponse(BaseModel):
    """Структурированный ответ диагностического агента."""

    bundle: DiagnosticBundle
    from_cache: bool


class EntryRequest(BaseModel):
    """Данные для входа пользователя в систему."""

    email: EmailStr


class EntryResponse(BaseModel):
    """Результат проверки пользователя по email."""

    user: User
    is_new: bool
    quiz_completed: bool = False


@app.get("/health", response_model=HealthResponse, tags=["service"])
def health_check() -> HealthResponse:
    """Возвращает статус сервиса."""
    logger.debug("Получен запрос /health")
    return HealthResponse(status="ok")


@app.post("/entry", response_model=EntryResponse, tags=["entry"])
def entrypoint(payload: EntryRequest) -> EntryResponse:
    """Проверяет наличие пользователя по email и создаёт его при необходимости."""
    normalized_email = str(payload.email).strip().lower()
    logger.info("Запрос входа для %s", normalized_email)

    existing = users.get_by_email(normalized_email)
    if existing:
        logger.info("Пользователь %s найден, возвращаем существующего", normalized_email)
        quiz = user_memory.get_quiz_profile(existing.user_id)
        quiz_completed = bool(quiz and quiz.completed)
        return EntryResponse(user=existing, is_new=False, quiz_completed=quiz_completed)

    logger.info("Пользователь %s не найден, создаём запись", normalized_email)
    created = users.create_user(UserCreate(external_id=normalized_email, email=normalized_email))
    return EntryResponse(user=created, is_new=True, quiz_completed=False)


@app.get("/quiz/questions", response_model=list[QuizQuestion], tags=["quiz"])
def list_quiz_questions() -> list[QuizQuestion]:
    """Возвращает полный список вопросов квиза."""
    logger.info("Получен запрос на список вопросов квиза")
    return get_quiz_questions()


@app.post("/quiz/submit", response_model=QuizSubmitResponse, tags=["quiz"])
def submit_quiz(payload: QuizSubmitRequest) -> QuizSubmitResponse:
    """
    Принимает ответы квиза, валидирует их и сохраняет в user_memory.

    Args:
        payload: пользователь, ответы, флаг перезаписи и версия.
    Returns:
        Статус завершения квиза и набор ответов.
    """

    user = users.get_by_id(payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = user_memory.get_quiz_profile(payload.user_id)
    if existing and existing.completed and not payload.force:
        logger.info("Квиз уже завершён user_id=%s, возврат кэша", payload.user_id)
        return QuizSubmitResponse(
            was_updated=False,
            completed=existing.completed,
            version=existing.version,
            completed_at=existing.completed_at,
            answers={key: answer.value for key, answer in existing.answers.items()},
        )

    if not payload.answers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Answers list is empty")

    raw_answers = [
        QuizAnswerModel(question_id=answer.question_id, value=answer.value)
        for answer in payload.answers
    ]
    try:
        validated = validate_answers(raw_answers)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    profile = run_quiz_for_user(
        user_id=payload.user_id,
        answers=validated.answers,
        version=payload.version or DEFAULT_QUIZ_VERSION,
        interactive=False,
    )
    logger.info("Квиз сохранён через API user_id=%s", payload.user_id)
    return QuizSubmitResponse(
        was_updated=True,
        completed=profile.completed,
        version=profile.version,
        completed_at=profile.completed_at,
        answers={key: answer.value for key, answer in profile.answers.items()},
    )


@app.post("/users", response_model=User, tags=["users"], status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> User:
    """Создаёт пользователя или возвращает существующего по email."""
    existing = users.get_by_email(payload.email)
    if existing:
        logger.info("Пользователь %s уже существует", payload.email)
        return existing
    return users.create_user(payload)


@app.get("/users/email/{email}", response_model=User, tags=["users"])
def get_user_by_email(email: EmailStr) -> User:
    """Возвращает пользователя по email."""
    user = users.get_by_email(str(email))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.get("/users/{user_id}", response_model=User, tags=["users"])
def get_user(user_id: UUID) -> User:
    """Возвращает пользователя по внутреннему идентификатору."""
    user = users.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.put("/users/{user_id}/profile", response_model=User, tags=["users"])
def update_profile(user_id: UUID, payload: ProfileRequest) -> User:
    """Обновляет профиль пользователя."""
    try:
        return users.update_profile(user_id, payload.profile_json)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.post(
    "/users/{user_id}/profile/enrich",
    response_model=ProfileEnrichmentResponse,
    tags=["users"],
)
def enrich_profile(
    user_id: UUID,
    payload: ProfileEnrichmentRequest,
) -> ProfileEnrichmentResponse:
    """
    Запускает LLM-обогащение profile_json пользователя.

    Args:
        user_id: Идентификатор пользователя.
        payload: Параметры запуска (force и доп. контекст).
    Returns:
        ProfileEnrichmentResponse: Итоговый профиль и признак, обновляли ли его.
    """

    try:
        result: EnsureProfileResult = ensure_profile_for_user(
            user_id=user_id,
            force=payload.force,
            extra_context=payload.extra_context,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return ProfileEnrichmentResponse(enriched=result.enriched, profile=result.profile)


@app.post(
    "/users/{user_id}/diagnostic/run",
    response_model=DiagnosticResponse,
    tags=["diagnostic"],
)
def run_diagnostic_endpoint(user_id: UUID, payload: DiagnosticRequest) -> DiagnosticResponse:
    """Запускает диагностический агент и сохраняет результат в память."""
    user = users.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.profile_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile is empty. Run enrichment first.",
        )
    bundle, from_cache = run_diagnostic_with_cache(user_id=user_id, force=payload.force)
    return DiagnosticResponse(bundle=bundle, from_cache=from_cache)


@app.post("/sessions", response_model=Session, tags=["sessions"], status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate) -> Session:
    """Создаёт новую сессию."""
    return sessions.create_session(payload)


@app.get("/sessions/{user_id}/active", response_model=Session | None, tags=["sessions"])
def get_active_session(user_id: UUID) -> Session | None:
    """Возвращает активную сессию пользователя, если она есть."""
    return sessions.get_active_session(user_id)


@app.post("/sessions/{session_id}/close", response_model=Session, tags=["sessions"])
def close_session(session_id: UUID, payload: CloseSessionRequest) -> Session:
    """Закрывает сессию с указанным статусом."""
    try:
        return sessions.close_session(session_id, payload.status, payload.ended_at)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.patch("/sessions/{session_id}/state", response_model=Session, tags=["sessions"])
def update_session_state(session_id: UUID, payload: UpdateStateRequest) -> Session:
    """Обновляет state_json сессии."""
    try:
        return sessions.update_state(session_id, payload.state_json)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@app.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessage,
    tags=["chat"],
    status_code=status.HTTP_201_CREATED,
)
def add_message(session_id: UUID, payload: ChatMessageRequest) -> ChatMessage:
    """Сохраняет сообщение в истории чата и добавляет его в долговременную память."""
    message = ChatMessageCreate(
        session_id=session_id,
        user_id=payload.user_id,
        sender=payload.sender,
        message_type=payload.message_type,
        payload=payload.payload,
        request_timestamp=payload.request_timestamp,
        response_timestamp=payload.response_timestamp,
        conversion_completed=payload.conversion_completed,
        expert_score=payload.expert_score,
        user_score=payload.user_score,
    )
    stored = chat_history.add_message(message)

    timestamp = stored.response_timestamp or stored.request_timestamp or datetime.now(timezone.utc)
    history_entry = {
        "role": stored.sender,
        "message_type": stored.message_type,
        "payload": stored.payload,
        "timestamp": timestamp,
    }
    user_memory.append_conversation_entry(stored.user_id, history_entry)
    return stored


@app.get("/sessions/{session_id}/messages", response_model=list[ChatMessage], tags=["chat"])
def get_session_messages(session_id: UUID, limit: int = 100) -> list[ChatMessage]:
    """Возвращает сообщения указанной сессии."""
    return chat_history.list_by_session(session_id, limit=limit)


@app.get("/users/{user_id}/messages", response_model=list[ChatMessage], tags=["chat"])
def get_user_messages(user_id: UUID, limit: int = 200) -> list[ChatMessage]:
    """Возвращает сообщения пользователя через все сессии."""
    return chat_history.list_by_user(user_id, limit=limit)


@app.get("/users/{user_id}/memory", response_model=UserMemory | None, tags=["memory"])
def get_memory(user_id: UUID) -> UserMemory | None:
    """Возвращает память пользователя, если она есть."""
    return user_memory.get_memory(user_id)


@app.put("/users/{user_id}/memory", response_model=UserMemory, tags=["memory"])
def upsert_memory(user_id: UUID, payload: MemoryRequest) -> UserMemory:
    """Создаёт или обновляет память пользователя."""
    request = UserMemoryUpsert(user_id=user_id, memory_data=payload.memory_data)
    return user_memory.upsert_memory(request)


@app.get(
    "/users/{user_id}/quiz-profile",
    response_model=QuizProfile | None,
    tags=["memory"],
)
def get_quiz_profile(user_id: UUID) -> QuizProfile | None:
    """Возвращает результаты квиза, если они есть."""
    return user_memory.get_quiz_profile(user_id)


@app.put(
    "/users/{user_id}/quiz-profile",
    response_model=QuizProfile,
    tags=["memory"],
)
def update_quiz_profile(user_id: UUID, payload: QuizProfileUpdate) -> QuizProfile:
    """Обновляет квиз-профиль пользователя."""
    return user_memory.upsert_quiz_profile(user_id, payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
