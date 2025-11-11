# Контекст проекта «Вместе» — backend v0.4

## Назначение проекта

LLM-сервис для персонализированной психологической поддержки с многошаговыми диалогами, долговременной памятью пользователя и рекомендациями контента. Workflow: **сбор данных → понимание контекста → поддержка → рекомендации**.

## Текущее состояние (v0.4)

**Реализовано:**
- ✅ REST API на FastAPI (12 эндпоинтов)
- ✅ PostgreSQL с полной схемой данных (11 таблиц)
- ✅ Слой доступа к БД через репозитории (5 штук)
- ✅ Долговременная память пользователя (user_memory)
- ✅ История диалогов (chat_history) с оценками качества
- ✅ Семейный квиз с версионированием
- ✅ CLI-демо с реальным LLM (OpenAI GPT-4.1 mini)
- ✅ Docker Compose с Chroma векторной БД
- ✅ Доменные модели для LLM (app/models/)
- ✅ LLM-сервисы на OpenAI Responses API:
  - ProfileEnrichmentService — генерация профиля из квиза
  - RecommendationAgentService — персонализация контента
  - DialogSummaryService — структурированное саммари
  - TherapyAgentService — терапевтическая поддержка

**В разработке:**
- ⏳ LangGraph workflow (оркестрация LLM-сервисов)
- ⏳ RAG с Chroma (таблица embedding_index_state готова)
- ⏳ YandexGPT как production LLM
- ⏳ Langfuse для трассировки
- ⏳ Redis для кэширования

---

## Архитектура

### Технологический стек

**Backend:**
- **FastAPI** — REST API, единственная точка входа
- **PostgreSQL 16** — транзакционные данные
- **Chroma** — векторное хранилище для RAG
- **psycopg3 + psycopg-pool** — асинхронный пул соединений
- **Pydantic v2** — валидация и модели данных

**LLM Integration:**
- **OpenAI GPT-4.1 mini** (текущая модель для тестирования)
- **YandexGPT** (планируется)
- **LangChain + LangGraph** (планируется)

**Инфраструктура:**
- **Docker Compose** — оркестрация контейнеров
- **Logging** — Python logging с уровнями INFO/DEBUG/ERROR

### Структура проекта

```
ВМЕСТЕ/
├── app/
│   ├── main.py                    # FastAPI эндпоинты
│   ├── models/                    # Pydantic схемы для LLM (NEW)
│   │   ├── user_profile.py        # Структура профиля
│   │   ├── recommendation.py      # Схемы офферов контента
│   │   ├── dialog_summary.py      # Схема саммари
│   │   └── therapy.py             # Схема терапевтического ответа
│   ├── services/                  # LLM-сервисы (NEW)
│   │   ├── profile_enrichment.py  # Генерация профиля из квиза
│   │   ├── recommendation_agent.py # Персонализация контента
│   │   ├── dialog_summary.py      # Структурированное саммари
│   │   └── therapy_agent.py       # Терапевтическая поддержка
│   └── db/
│       ├── connection.py          # Пул psycopg-pool
│       ├── models.py              # Схема БД (User, Session, etc.)
│       └── repositories/
│           ├── users.py
│           ├── sessions.py
│           ├── chat_history.py
│           ├── user_memory.py
│           └── psychologist_content.py  # (NEW)
├── config.py                      # Настройки (добавлена openai_model)
├── db/init.sql                    # Схема БД (281 строка, 11 таблиц)
├── docker-compose.yml, Dockerfile
└── README.md, AGENTS.md
```

---

## LLM-сервисы (app/services/)

**Архитектура:** Все сервисы используют OpenAI Responses API с `response_format` для structured outputs.

### 1. ProfileEnrichmentService (profile_enrichment.py)
- **Назначение:** Генерация `profile_json` из ответов квиза
- **API:** `enrich_user_profile(user_id, quiz_answers)` → UserProfileModel
- **Сохраняет:** `users.profile_json`

### 2. RecommendationAgentService (recommendation_agent.py)
- **Назначение:** Подбор контента психолога под профиль пользователя
- **API:** `run_content_recommendation(user_id, tone_voice, limit)` → RecommendationReply
- **Использует:** `users.profile_json` + `psychologist_content.list_available()`

### 3. DialogSummaryService (dialog_summary.py)
- **Назначение:** Структурированное саммари диалога для долговременной памяти
- **API:** `summarize_dialog(user_id, session_id, limit)` → DialogSummary
- **Сохраняет:** `user_memory.memory_data["dialog_summary"]`

### 4. TherapyAgentService (therapy_agent.py)
- **Назначение:** Эмпатичный ответ поддержки на основе полного контекста
- **Контекст:** профиль + саммари + последние N сообщений
- **API:** `run_therapy_agent(user_id, history_limit)` → TherapyReply
- **Учитывает:** `risk_flags` из профиля для безопасных рекомендаций

**Модели данных (app/models/):**
- `UserProfileModel` — stress_level, emotional_tone, key_concerns, support_needs, risk_flags, etc.
- `DialogSummary` — emotional_state, key_events, user_goals, blockers, next_steps
- `RecommendationReply` — message, offer (why, expected_result, cta), follow_up_question
- `TherapyReply` — message, coping_tips, follow_up_questions, next_step

**Демо:**
```bash
export VMESTE_DEMO_USER_ID=469a0f1d-01de-4340-8e8d-e5897eb43d52
python -m app.services.profile_enrichment
python -m app.services.recommendation_agent
python -m app.services.dialog_summary
python -m app.services.therapy_agent
```

---

## База данных (PostgreSQL)

### Таблицы и назначение

**Пользователи и сессии:**
- `users` — карточка пользователя (external_id, email, profile_json)
- `sessions` — сессии диалога (mode: intake/consultation/support, status, state_json для LangGraph)
- `chat_history` — все сообщения (sender: user/assistant, payload, expert_score, user_score)
- `user_memory` — долговременная память (JSONB: conversation_history, quiz_profile, и т.д.)

**Контент и RAG:**
- `sources` — исходные материалы (видео, статьи, URL, метаданные)
- `documents` — тексты после транскрибации
- `content_chunks` — фрагменты для RAG (тема, TOV, метаданные)
- `chunk_embeddings_meta` — связь с Chroma коллекциями
- `embedding_index_state` — метаданные индексации эмбеддингов (record_type, collection_name, needs_sync)

**Каталог и стиль:**
- `psychologist_content` — платные материалы (описание, цена, теги, URL)
- `style_examples` — эталонные Q/A для tone-of-voice

### Ключевые особенности

- **JSONB колонки** для гибких данных (profile_json, state_json, memory_data)
- **UUID** как первичные ключи
- **Soft delete** (is_deleted флаги)
- **Timestamps** (created_at, updated_at) с автоматическим NOW()
- **Индексы** на external_id, user_id, session_id для быстрых запросов

---

## Слой доступа к БД

### Connection Pool (app/db/connection.py)

```python
# Пул psycopg-pool с min_size=1, max_size=5
_pool = ConnectionPool(conninfo=settings.postgres_dsn, ...)

# Утилиты:
fetch_all(query, params) -> list[DictRow]
fetch_one(query, params) -> DictRow | None
execute(query, params) -> None
fetch_many(query, params_seq) -> list[list[DictRow]]
```

### Репозитории (Repository Pattern)

**users.py:**
- `create_user(UserCreate)` → User
- `get_by_external_id(str)` → User | None
- `get_by_email(str)` → User | None
- `update_profile(user_id, dict)` → User

**sessions.py:**
- `create_session(SessionCreate)` → Session
- `get_active_session(user_id)` → Session | None
- `close_session(session_id, status)` → Session
- `update_state(session_id, state_json)` → Session

**chat_history.py:**
- `add_message(ChatMessageCreate)` → ChatMessage
- `list_by_session(session_id, limit)` → list[ChatMessage]
- `list_by_user(user_id, limit)` → list[ChatMessage]

**user_memory.py:**
- `get_memory(user_id)` → UserMemory | None
- `upsert_memory(UserMemoryUpsert)` → UserMemory
- `append_conversation_entry(user_id, entry)` → UserMemory  # автоматически добавляет в историю
- `get_quiz_profile(user_id)` → QuizProfile | None
- `upsert_quiz_profile(user_id, QuizProfileUpdate)` → QuizProfile

**psychologist_content.py:**
- `list_available(limit)` → list[dict] — выборка активных материалов для рекомендаций

---

## API Endpoints (v0.4)

**Базовые:**
- `GET /health` — статус сервиса

**Пользователи:**
- `POST /users` — создать или вернуть существующего по email
- `GET /users/email/{email}` — получить по email
- `GET /users/{user_id}` — получить по UUID
- `PUT /users/{user_id}/profile` — обновить profile_json

**Сессии:**
- `POST /sessions` — создать сессию (mode, status)
- `GET /sessions/{user_id}/active` — активная сессия
- `POST /sessions/{session_id}/close` — завершить
- `PATCH /sessions/{session_id}/state` — обновить state_json

**Чат:**
- `POST /sessions/{session_id}/messages` — записать сообщение + автоматически в user_memory
- `GET /sessions/{session_id}/messages` — история сессии
- `GET /users/{user_id}/messages` — история пользователя

**Память:**
- `GET /users/{user_id}/memory` — получить memory_data
- `PUT /users/{user_id}/memory` — обновить memory_data

**Квиз:**
- `GET /users/{user_id}/quiz-profile` — получить ответы квиза
- `PUT /users/{user_id}/quiz-profile` — обновить ответы

---

## Долговременная память (user_memory)

### Структура memory_data (JSONB)

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
    "answers": {
      "family_structure": {
        "question": "...",
        "answer": "...",
        "confidence": 0.9,
        "meta": {}
      }
    },
    "updated_at": "ISO8601"
  }
}
```

### Автоматическое сохранение

При каждом `POST /sessions/{session_id}/messages`:
1. Сообщение записывается в `chat_history`
2. **Автоматически** вызывается `append_conversation_entry()` → добавляет в `user_memory.conversation_history`
3. История обрезается до max_length=2000 сообщений

---

## Семейный квиз

### Модель данных

**QuizAnswer:**
- question (str)
- answer (str | list | dict)
- confidence (float, 0-1)
- meta (dict)

**QuizProfile:**
- version (str)
- completed (bool)
- answers (dict[str, QuizAnswer])
- updated_at (datetime)

### Workflow

1. `PUT /users/{user_id}/quiz-profile` с частичными ответами
2. `upsert_quiz_profile()` умно мерджит с существующими данными
3. Флаг `completed` можно выставить вручную
4. Версионирование позволяет обновлять схему квиза

---

## Скрипты и демо

### chat_cli.py

**Назначение:** Интерактивный чат с реальным LLM через API.

**Workflow:**
1. Вводится email → создаётся/находится пользователь
2. Загружается история из `user_memory.conversation_history` (до 40 сообщений)
3. При каждом сообщении: добавляется в `chat_history` и отправляется в OpenAI GPT-4.1 mini
4. При выходе — сессия закрывается

**Запуск:**
```bash
export OPENAI_API_KEY=sk-...
python scripts/chat_cli.py
```

### quiz_demo.py

**Назначение:** Демонстрация заполнения семейного квиза через HTTP API.

**Запуск:**
```bash
python scripts/quiz_demo.py
```

---

## Запуск приложения

### Локальная разработка

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Поднять только БД через Docker
docker compose up postgres -d

# 3. Запустить API локально
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Проверить
curl http://localhost:8000/health  # {"status":"ok"}
```

### Docker Compose (полное окружение)

```bash
# Создать .env файл (опционально, есть дефолты)
cp .env.example .env

# Поднять все сервисы
docker compose up --build

# Доступные порты:
# - API: http://localhost:8000
# - Chroma: http://localhost:8001
# - PostgreSQL: localhost:5432
```

### Проверка слоя БД

```bash
docker compose up postgres -d
python -m app.db.connection          # проверка пула
python -m app.db.repositories.users  # создать тестового пользователя
docker compose down
```

---

## Конфигурация (config.py)

**Переменные окружения (.env):**
```bash
APP_ENV=development|production|test
POSTGRES_HOST=localhost  # vmeste-postgres в Docker
POSTGRES_PORT=5432
POSTGRES_DB=vmeste
POSTGRES_USER=vmeste
POSTGRES_PASSWORD=vmeste_password
OPENAI_API_KEY=sk-...       # для LLM-сервисов
OPENAI_MODEL=gpt-4.1-mini   # по умолчанию
```

**Singleton настройки:**
```python
from config import get_settings
settings = get_settings()
dsn = settings.postgres_dsn
```

---

## История разработки (последние коммиты)

### 351bf3f — feat: терапевтический агент + фиксы Pydantic
- Модель TherapyReply и сервис TherapyAgentService
- Трёхуровневый контекст (профиль + саммари + последние сообщения)
- Учёт risk_flags из профиля для безопасных рекомендаций
- Исправлен доступ к атрибутам ChatMessage в dialog_summary
- Удалён устаревший ensure_ascii=False из Pydantic

### 2af92ef — feat: реализованы LLM-сервисы (профиль, рекомендации, саммари)
- ProfileEnrichmentService для генерации profile_json из квиза
- RecommendationAgentService для подбора контента
- DialogSummaryService для структурированного саммари
- Все сервисы используют OpenAI Responses API с structured outputs

### acc70a5 — feat: добавлены доменные модели и репозиторий контента
- Pydantic-схемы: UserProfileModel, DialogSummary, RecommendationReply
- Репозиторий psychologist_content.list_available()
- Трёхслойная архитектура: DB → Models → Services

### 44c476f — feat: добавлена инфраструктура для LLM-сервисов
- config.py: настройка openai_model (по умолчанию gpt-4.1-mini)
- db/init.sql: таблица embedding_index_state для синхронизации эмбеддингов
- .gitignore: исключение scripts/conversation_runner.py
- AGENTS.md: правила лаконичности и устаревший ensure_ascii

### e32a5e5 — feat: семейный квиз
- Модели QuizAnswer, QuizProfile с версионированием
- API endpoints для квиза

---

## Текущие ограничения и планы

**Ограничения:**
- LangGraph workflow не реализован (есть отдельные LLM-сервисы)
- RAG с Chroma не подключен (таблица embedding_index_state готова)
- Используется OpenAI (нет YandexGPT)
- Нет Redis для кэширования
- Нет Langfuse для трассировки

**Планы:**
1. Оркестрация LLM-сервисов через LangGraph
2. Векторизация контента и интеграция RAG с Chroma
3. Few-shot примеры для TOV из style_examples
4. YandexGPT как production LLM (замена OpenAI)
5. Langfuse для трассировки цепочек
6. Redis для кэширования профилей и саммари

---

## Полезные команды

```bash
# Логи контейнеров
docker compose logs -f api
docker compose logs -f postgres

# Подключение к PostgreSQL
docker exec -it vmeste-postgres psql -U vmeste -d vmeste

# Просмотр таблиц
\dt

# Просмотр памяти пользователя
SELECT external_id, jsonb_pretty(memory_data)
FROM users u
JOIN user_memory m ON u.user_id = m.user_id;

# Перезапуск API без rebuild
docker compose restart api

# Очистка volumes (УДАЛИТ ДАННЫЕ!)
docker compose down -v
```

---

## Ключевые файлы для изучения

**Точка входа:**
- `app/main.py` — FastAPI эндпоинты

**LLM-сервисы:**
- `app/services/profile_enrichment.py` — генерация профиля из квиза
- `app/services/recommendation_agent.py` — персонализация контента
- `app/services/therapy_agent.py` — терапевтическая поддержка
- `app/services/dialog_summary.py` — сжатие диалогов

**Доменные модели:**
- `app/models/user_profile.py` — схема профиля для LLM
- `app/models/recommendation.py` — схемы офферов контента
- `app/models/therapy.py` — схема терапевтического ответа

**БД:**
- `app/db/models.py` — User, Session, ChatMessage, QuizProfile
- `app/db/repositories/` — CRUD операции
- `db/init.sql` — полная схема БД

**Конфигурация:**
- `config.py` — настройки приложения

---

## Глоссарий

- **intake** — режим сбора информации о пользователе
- **consultation** — режим консультации с психологом
- **support** — режим поддерживающего диалога
- **TOV** (tone-of-voice) — стиль общения
- **RAG** (Retrieval-Augmented Generation) — генерация с извлечением контекста
- **conversation_history** — история диалогов в user_memory
- **quiz_profile** — ответы на семейный квиз в user_memory
- **state_json** — состояние LangGraph в сессии
- **external_id** — внешний идентификатор пользователя (email)

---

---

## ⚠️ ВАЖНО: Правила разработки

**Перед началом работы ОБЯЗАТЕЛЬНО прочитайте `AGENTS.md`** — он содержит критически важные правила:
- Процесс работы (анализ → планирование → реализация → самопроверка)
- Принципы простоты и обучения
- Стандарты кодирования и комментирования
- Требования к логированию
- Структуру agent_meta блоков

**Без ознакомления с AGENTS.md работа над проектом ЗАПРЕЩЕНА.**

---

**Версия документа:** 2025-11-11
**Версия API:** 0.4.0
**Последний коммит:** 351bf3f (feat: терапевтический агент)
