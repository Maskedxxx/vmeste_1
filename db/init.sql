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

-- Документы после транскрибации/нормализации.
CREATE TABLE IF NOT EXISTS documents (
    -- PK документа.
    doc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- FK → sources.source_id: из какого источника получен документ.
    source_id UUID NOT NULL REFERENCES sources(source_id),
    -- Полный очищенный текст.
    raw_text TEXT NOT NULL,
    -- Путь к исходному файлу или объекту в сторидже (может быть NULL).
    storage_path TEXT NULL,
    -- Статус обработки: raw / cleaned / ready и т.д.
    status TEXT NOT NULL,
    -- Дополнительные метаданные (инструмент обработки, номер части и т.п.).
    meta JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Контроль дубликатов (например, SHA256 от текста).
    checksum TEXT NULL,
    -- Таймстемпы и soft delete.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS documents_source_id_idx ON documents(source_id);
CREATE UNIQUE INDEX IF NOT EXISTS documents_checksum_idx
    ON documents(checksum) WHERE checksum IS NOT NULL;

-- Чанки контента, используемые в RAG.
CREATE TABLE IF NOT EXISTS content_chunks (
    -- PK чанка.
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- FK → documents.doc_id: из какого документа нарезан чанк.
    doc_id UUID NOT NULL REFERENCES documents(doc_id),
    -- Порядковый номер внутри документа.
    sequence INTEGER NOT NULL,
    -- Основной текст чанка.
    text TEXT NOT NULL,
    -- Краткая выжимка.
    summary TEXT NULL,
    -- Определённая тема и уверенность классификатора.
    topic TEXT NULL,
    topic_conf NUMERIC(3, 2) NULL,
    -- Оценка соответствия тону автора.
    tov_score NUMERIC(3, 2) NULL,
    -- Тип контента: lesson / video / post / case / faq и т.д.
    content_type TEXT NULL,
    -- Ключевые слова (JSON-список).
    keywords JSONB NOT NULL DEFAULT '[]'::JSONB,
    -- Флаг успешной очистки/валидации.
    cleaned BOOLEAN NOT NULL DEFAULT FALSE,
    -- Дополнительные атрибуты (размер, версия и т.д.).
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Таймстемпы и soft delete.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS content_chunks_doc_idx
    ON content_chunks(doc_id, sequence);
CREATE INDEX IF NOT EXISTS content_chunks_topic_idx
    ON content_chunks(topic);

-- Мета-информация об эмбеддингах в Chroma.
CREATE TABLE IF NOT EXISTS chunk_embeddings_meta (
    -- PK, совпадает с идентификатором векторов в Chroma.
    embedding_id UUID PRIMARY KEY,
    -- FK → content_chunks.chunk_id.
    chunk_id UUID NOT NULL REFERENCES content_chunks(chunk_id),
    -- Имя коллекции: content_all / faq_basic / personal_embedding и др.
    collection_name TEXT NOT NULL,
    -- Метаданные о модели эмбеддинга.
    embedding_provider TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    -- Время последней индексации.
    indexed_at TIMESTAMPTZ NOT NULL,
    -- Флаг, что чанк нужно повторно синхронизировать.
    needs_sync BOOLEAN NOT NULL DEFAULT FALSE,
    -- Дополнительные сведения (версии, ошибки).
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Soft delete для удаления векторов.
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX IF NOT EXISTS chunk_embeddings_chunk_idx
    ON chunk_embeddings_meta(chunk_id, collection_name);

-- Каталог материалов психолога (витрина).
CREATE TABLE IF NOT EXISTS psychologist_content (
    -- PK карточки каталога.
    content_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Опциональная связь с исходным материалом.
    source_id UUID NULL REFERENCES sources(source_id),
    -- Заголовок карточки.
    title TEXT NOT NULL,
    -- Краткое описание (используется в превью).
    summary TEXT NULL,
    -- Полный текст описания для каталога.
    description TEXT NULL,
    -- Тип контента: lesson / webinar / article / course / consultation.
    content_type TEXT NOT NULL,
    -- Основная тема (стресс, отношения и т.д.).
    topic TEXT NULL,
    -- Теги для фильтрации и поиска.
    tags JSONB NOT NULL DEFAULT '[]'::JSONB,
    -- Стоимость и валюта (NULL, если материал бесплатный).
    price NUMERIC(10, 2) NULL,
    currency TEXT NULL DEFAULT 'RUB',
    -- Ссылки на лендинг/материал/медиаприложения.
    url TEXT NULL,
    media_url TEXT NULL,
    thumbnail_url TEXT NULL,
    -- Длительность (для видео/уроков).
    duration_minutes INTEGER NULL,
    -- Флаг доступности в каталоге.
    available BOOLEAN NOT NULL DEFAULT TRUE,
    -- Дополнительные бизнес-атрибуты.
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Таймстемпы и soft delete.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS psychologist_content_topic_idx
    ON psychologist_content(topic);

-- Эталоны стиля общения (few-shot TOV).
CREATE TABLE IF NOT EXISTS style_examples (
    -- PK эталонного примера.
    example_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Тема, к которой относится пример.
    topic TEXT NOT NULL,
    -- Пример вопроса пользователя.
    question TEXT NOT NULL,
    -- Эталонный ответ в нужном тоне.
    answer TEXT NOT NULL,
    -- Оценка соответствия TOV (0..1).
    tov_score NUMERIC(3, 2) NOT NULL,
    -- Дополнительные флаги (эмпатия, запреты и т.д.).
    flags JSONB NOT NULL DEFAULT '[]'::JSONB,
    -- Ссылка на источник (URL, идентификатор документа).
    source_ref TEXT NULL,
    -- Дополнительные сведения.
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Таймстемпы и признак активности.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS style_examples_topic_idx
    ON style_examples(topic);
