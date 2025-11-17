# Схема базы данных «Вместе»

## Обзор

**СУБД:** PostgreSQL 16  
**Расширения:** uuid-ossp (генерация UUID)  
**Файл схемы:** db/init.sql

---

## Диаграмма связей

```
sources ───┐
           ↓
        documents ───> content_chunks ───> chunk_embeddings_meta
           ↑                                 embedding_index_state
psychologist_content

users ───> sessions ───> chat_history
  │            │
  └──> user_memory

style_examples (независимая таблица)
```

---

## Таблицы

### sources
**Назначение:** Источники контента (видео, статьи, подкасты).

**Поля:**
- `source_id` UUID PK — уникальный идентификатор
- `source_type` TEXT NOT NULL — тип (video / podcast / post / article / document)
- `title` TEXT NOT NULL — название
- `url` TEXT NULL — ссылка на оригинал
- `meta` JSONB DEFAULT '{}' — метаданные (длительность, автор, канал)
- `created_at`, `updated_at` TIMESTAMPTZ
- `is_deleted` BOOLEAN DEFAULT FALSE — soft delete

**Индексы:** нет дополнительных

---

### documents
**Назначение:** Транскрибированные и нормализованные тексты из источников.

**Поля:**
- `doc_id` UUID PK
- `source_id` UUID NOT NULL FK → sources.source_id
- `raw_text` TEXT NOT NULL — полный очищенный текст
- `storage_path` TEXT NULL — путь к файлу в сторидже
- `status` TEXT NOT NULL — статус обработки (raw / cleaned / ready)
- `meta` JSONB DEFAULT '{}' — инструмент обработки, номер части
- `checksum` TEXT NULL — SHA256 для контроля дубликатов
- `created_at`, `updated_at` TIMESTAMPTZ
- `is_deleted` BOOLEAN DEFAULT FALSE

**Индексы:**
- `documents_source_id_idx` ON (source_id)
- `documents_checksum_idx` UNIQUE ON (checksum) WHERE checksum IS NOT NULL

---

### content_chunks
**Назначение:** Фрагменты документов для RAG (Retrieval-Augmented Generation).

**Поля:**
- `chunk_id` UUID PK
- `doc_id` UUID NOT NULL FK → documents.doc_id
- `sequence` INTEGER NOT NULL — порядковый номер в документе
- `text` TEXT NOT NULL — основной текст чанка
- `summary` TEXT NULL — краткая выжимка
- `topic` TEXT NULL — определенная тема
- `topic_conf` NUMERIC(3,2) NULL — уверенность классификатора (0.00-1.00)
- `tov_score` NUMERIC(3,2) NULL — оценка соответствия тону автора
- `content_type` TEXT NULL — lesson / video / post / case / faq
- `keywords` JSONB DEFAULT '[]' — список ключевых слов
- `cleaned` BOOLEAN DEFAULT FALSE — флаг успешной очистки
- `metadata` JSONB DEFAULT '{}' — размер, версия и т.д.
- `created_at`, `updated_at` TIMESTAMPTZ
- `is_deleted` BOOLEAN DEFAULT FALSE

**Индексы:**
- `content_chunks_doc_idx` ON (doc_id, sequence)
- `content_chunks_topic_idx` ON (topic)

---

### chunk_embeddings_meta
**Назначение:** Метаинформация о векторных эмбеддингах в Chroma.

**Поля:**
- `embedding_id` UUID PK — совпадает с ID в Chroma
- `chunk_id` UUID NOT NULL FK → content_chunks.chunk_id
- `collection_name` TEXT NOT NULL — имя коллекции (content_all / faq_basic / personal_embedding)
- `embedding_provider` TEXT NOT NULL — модель эмбеддинга
- `embedding_dim` INTEGER NOT NULL — размерность вектора
- `indexed_at` TIMESTAMPTZ NOT NULL — время индексации
- `needs_sync` BOOLEAN DEFAULT FALSE — требуется ре-индексация
- `metadata` JSONB DEFAULT '{}' — версии, ошибки
- `is_deleted` BOOLEAN DEFAULT FALSE

**Индексы:**
- `chunk_embeddings_chunk_idx` UNIQUE ON (chunk_id, collection_name)

---

### embedding_index_state
**Назначение:** Состояние индексации эмбеддингов (универсальная таблица).

**Поля:**
- `embedding_id` UUID PK
- `record_type` TEXT NOT NULL — тип записи (chunk / document / user)
- `record_id` TEXT NOT NULL — идентификатор записи
- `collection_name` TEXT NOT NULL
- `embedding_provider` TEXT NOT NULL
- `embedding_dim` INTEGER NOT NULL
- `indexed_at` TIMESTAMPTZ DEFAULT NOW()
- `needs_sync` BOOLEAN DEFAULT FALSE
- `metadata` JSONB DEFAULT '{}'
- `is_deleted` BOOLEAN DEFAULT FALSE

**Индексы:**
- UNIQUE (record_type, record_id, collection_name)

---

### users
**Назначение:** Карточки пользователей платформы.

**Поля:**
- `user_id` UUID PK
- `external_id` TEXT NOT NULL UNIQUE — внешний идентификатор (email / Telegram ID)
- `email` TEXT NOT NULL UNIQUE — primary login
- `profile_json` JSONB NOT NULL — структурированный профиль (интейк, теги, TOV)
- `created_at`, `updated_at` TIMESTAMPTZ

**Индексы:**
- UNIQUE на external_id
- UNIQUE на email

---

### sessions
**Назначение:** Сессии общения и workflow пользователя.

**Поля:**
- `session_id` UUID PK
- `user_id` UUID NOT NULL FK → users.user_id
- `mode` TEXT NOT NULL — режим (intake / consultation / support)
- `status` TEXT NOT NULL — статус (active / completed / aborted)
- `state_json` JSONB DEFAULT '{}' — состояние LangGraph
- `started_at` TIMESTAMPTZ DEFAULT NOW()
- `ended_at` TIMESTAMPTZ NULL

**Индексы:**
- `sessions_user_id_idx` ON (user_id)

---

### chat_history
**Назначение:** История всех сообщений в диалогах.

**Поля:**
- `message_id` UUID PK
- `session_id` UUID NOT NULL FK → sessions.session_id
- `user_id` UUID NOT NULL FK → users.user_id
- `sender` TEXT NOT NULL — user / assistant
- `message_type` TEXT NOT NULL — text / recommendation / summary
- `payload` JSONB NOT NULL — текст, офферы, метаинформация
- `request_timestamp` TIMESTAMPTZ DEFAULT NOW()
- `response_timestamp` TIMESTAMPTZ NULL
- `conversion_completed` BOOLEAN DEFAULT FALSE — флаг конверсии
- `expert_score` SMALLINT NULL — оценка эксперта (1-5)
- `user_score` SMALLINT NULL — оценка пользователя (1-5)

**Ограничения:**
- CHECK expert_score IS NULL OR (expert_score BETWEEN 1 AND 5)
- CHECK user_score IS NULL OR (user_score BETWEEN 1 AND 5)

**Индексы:**
- `chat_history_session_idx` ON (session_id, request_timestamp)
- `chat_history_user_idx` ON (user_id, request_timestamp)

---

### user_memory
**Назначение:** Долговременная память пользователя (агрегированные факты).

**Поля:**
- `memory_id` UUID PK
- `user_id` UUID NOT NULL UNIQUE FK → users.user_id
- `memory_data` JSONB NOT NULL — структурированные данные (см. ниже)
- `created_at`, `updated_at` TIMESTAMPTZ

**Структура memory_data:**
```json
{
  "conversation_history": [
    {
      "role": "user|assistant",
      "message_type": "text",
      "payload": { "text": "..." },
      "timestamp": "ISO8601"
    }
  ],
"quiz_profile": {
    "version": "1.0",
    "completed": false,
    "completed_at": null,
    "answers": {
      "question_id": {
        "value": "...",
        "confidence": 0.9,
        "updated_at": "ISO8601"
      }
    },
    "meta": {}
  },
  "diagnostic_bundle": {
    "body": { "analysis": "...", "recommended_doctors": [], "recommended_tests": [], "possible_physiology": [], "tags": [] },
    "mind": { "analysis": "...", "tags": [] },
    "sex": { "analysis": "...", "tags": [] },
    "generated_at": "ISO8601"
  },
  "week_plan": {
    "tags": ["стресс", "усталость"],
    "plan": { "days": [ { "day": 1, "content_id": "...", "title": "...", "goal": "...", "instructions": "...", "tags": [] }, ... ] },
    "generated_at": "ISO8601"
  }
}
```

**Связь:** 1:1 с users (один пользователь = одна память)

---

### psychologist_content
**Назначение:** Каталог платных материалов психолога (витрина).

**Поля:**
- `content_id` UUID PK
- `source_id` UUID NULL FK → sources.source_id — связь с исходным материалом
- `title` TEXT NOT NULL — заголовок
- `summary` TEXT NULL — краткое описание для превью
- `description` TEXT NULL — полное описание
- `content_type` TEXT NOT NULL — lesson / webinar / article / course / consultation
- `topic` TEXT NULL — основная тема (стресс, отношения)
- `tags` JSONB DEFAULT '[]' — теги для фильтрации
- `price` NUMERIC(10,2) NULL — стоимость (NULL если бесплатно)
- `currency` TEXT DEFAULT 'RUB'
- `url` TEXT NULL — ссылка на лендинг
- `media_url` TEXT NULL — ссылка на медиафайл
- `thumbnail_url` TEXT NULL — превью
- `duration_minutes` INTEGER NULL — длительность (для видео/уроков)
- `available` BOOLEAN DEFAULT TRUE — доступность в каталоге
- `metadata` JSONB DEFAULT '{}' — дополнительные атрибуты
- `created_at`, `updated_at` TIMESTAMPTZ
- `is_deleted` BOOLEAN DEFAULT FALSE

**Индексы:**
- `psychologist_content_topic_idx` ON (topic)

---

### style_examples
**Назначение:** Эталоны стиля общения (few-shot TOV для LLM).

**Поля:**
- `example_id` UUID PK
- `topic` TEXT NOT NULL — тема примера
- `question` TEXT NOT NULL — пример вопроса пользователя
- `answer` TEXT NOT NULL — эталонный ответ в нужном тоне
- `tov_score` NUMERIC(3,2) NOT NULL — оценка соответствия TOV (0.00-1.00)
- `flags` JSONB DEFAULT '[]' — флаги (эмпатия, запреты)
- `source_ref` TEXT NULL — ссылка на источник
- `metadata` JSONB DEFAULT '{}'
- `created_at`, `updated_at` TIMESTAMPTZ
- `is_active` BOOLEAN DEFAULT TRUE — признак активности

**Индексы:**
- `style_examples_topic_idx` ON (topic)

---

## Связи между таблицами (Foreign Keys)

### Контент и RAG
- `documents.source_id` → `sources.source_id`
- `content_chunks.doc_id` → `documents.doc_id`
- `chunk_embeddings_meta.chunk_id` → `content_chunks.chunk_id`
- `psychologist_content.source_id` → `sources.source_id` (опциональная)

### Пользователи и диалоги
- `sessions.user_id` → `users.user_id`
- `chat_history.session_id` → `sessions.session_id`
- `chat_history.user_id` → `users.user_id`
- `user_memory.user_id` → `users.user_id` (UNIQUE, 1:1)

---

## Ключевые особенности

### JSONB колонки
**Гибкое хранение структурированных данных:**
- `users.profile_json` — профиль пользователя (стресс, интересы, TOV)
- `sessions.state_json` — состояние LangGraph workflow
- `chat_history.payload` — содержимое сообщений
- `user_memory.memory_data` — история и квиз
- `content_chunks.keywords` — ключевые слова
- `psychologist_content.tags` — теги для фильтрации

### UUID как Primary Keys
Все таблицы используют UUID (uuid_generate_v4()) для уникальности и распределенности.

### Soft Delete
Большинство таблиц имеют флаг `is_deleted` для мягкого удаления данных.

### Timestamps
Автоматические `created_at` и `updated_at` (с NOW() и ON UPDATE).

### Индексы для производительности
- По внешним ключам (user_id, session_id)
- По времени (request_timestamp)
- По темам (topic)
- По уникальным полям (external_id, email, checksum)

### CHECK constraints
Валидация диапазонов на уровне БД:
- `expert_score` и `user_score`: 1-5 или NULL

### Инициализация
При запуске создается тестовый пользователь:
```sql
INSERT INTO users (external_id, email, profile_json)
VALUES ('test-user', 'test-user@example.com', '{}'::JSONB)
ON CONFLICT (external_id) DO NOTHING;
```

---

## Миграции и обслуживание

**Схема применяется:** автоматически при старте контейнера postgres через docker-compose.

**Проверка подключения:**
```sql
SELECT 1 AS ready;
```

---

**Версия документа:** 2025-11-13  
**Схема БД:** db/init.sql (282 строки, 10 таблиц)
