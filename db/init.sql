-- Схема пользовательского взаимодействия (PostgreSQL).
-- Таблицы создаются автоматически при старте контейнера БД.

-- Расширение для генерации UUID (используем в PK).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Источники контента: фиксируют происхождение материалов.
CREATE TABLE IF NOT EXISTS sources (
    -- PK: уникальный идентификатор источника.
    source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Тип источника: video / podcast / post / article / document и т.д.
    source_type TEXT NOT NULL,
    -- Человекочитаемое название или описание.
    title TEXT NOT NULL,
    -- Ссылка на оригинал (может быть NULL для локальных материалов).
    url TEXT NULL,
    -- Дополнительные метаданные: длительность, автор, канал и т.д.
    meta JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Таймстемпы создания/обновления записи.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Флаг мягкого удаления (оставляем запись для истории).
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- Пользователи платформы: один ряд = один пользователь.
CREATE TABLE IF NOT EXISTS users (
    -- PK: user_id, генерируется uuid_generate_v4().
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Уникальный внешний идентификатор (например, Telegram ID).
    external_id TEXT NOT NULL UNIQUE,
    -- Профиль пользователя (интейк, теги, tov и т.д.).
    profile_json JSONB NOT NULL,
    -- Таймстемпы создания/обновления карточки.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Сессии общения: связывают пользователя и состояние workflow.
CREATE TABLE IF NOT EXISTS sessions (
    -- PK с автогенерацией UUID.
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- FK → users.user_id: владелец сессии.
    user_id UUID NOT NULL REFERENCES users(user_id),
    -- Режим: intake / consultation / support.
    mode TEXT NOT NULL,
    -- Статус сессии: active / completed / aborted и т.п.
   status TEXT NOT NULL,
    -- Текущее состояние графа в JSON.
    state_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Временные метки начала/окончания.
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ NULL
);

-- Индекс для быстрого поиска сессий пользователя.
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);

-- История сообщений: хранит каждую реплику в диалоге.
CREATE TABLE IF NOT EXISTS chat_history (
    -- PK с UUID.
    message_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- FK → sessions.session_id: принадлежность реплики сессии.
    session_id UUID NOT NULL REFERENCES sessions(session_id),
    -- FK → users.user_id: быстрое получение сообщений пользователя.
    user_id UUID NOT NULL REFERENCES users(user_id),
    -- Отправитель: user / assistant.
    sender TEXT NOT NULL,
    -- Тип сообщения: text / recommendation / summary и др.
    message_type TEXT NOT NULL,
    -- Полезная нагрузка (текст, офферы, метаинформация).
    payload JSONB NOT NULL,
    -- Таймстемпы запроса и ответа (latency и хронология).
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_timestamp TIMESTAMPTZ NULL,
    -- Флаг успешной конверсии.
    conversion_completed BOOLEAN NOT NULL DEFAULT FALSE,
    -- Оценки качества от эксперта и пользователя.
    expert_score SMALLINT NULL,
    user_score SMALLINT NULL,
    -- Контроль диапазона оценок 1–5 (если заданы).
    CONSTRAINT expert_score_range CHECK (
        expert_score IS NULL OR (expert_score BETWEEN 1 AND 5)
    ),
    CONSTRAINT user_score_range CHECK (
        user_score IS NULL OR (user_score BETWEEN 1 AND 5)
    )
);

-- Индексы для выборок по сессиям и пользователям.
CREATE INDEX IF NOT EXISTS chat_history_session_idx
    ON chat_history(session_id, request_timestamp);

CREATE INDEX IF NOT EXISTS chat_history_user_idx
    ON chat_history(user_id, request_timestamp);

-- Долговременная память пользователя (агрегированные факты).
CREATE TABLE IF NOT EXISTS user_memory (
    -- PK с UUID.
    memory_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- FK → users.user_id, один пользователь ↔ одна память.
    user_id UUID NOT NULL UNIQUE REFERENCES users(user_id),
    -- JSONB со структурированными данными (стресс, триггеры и т.д.).
    memory_data JSONB NOT NULL,
    -- Таймстемпы создания и обновления памяти.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
