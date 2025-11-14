# Архитектура приложения «Вместе»

## Обзор

LLM-сервис для персонализированной психологической поддержки на базе FastAPI с PostgreSQL, реализующий паттерн Repository для доступа к данным.

**Версия:** 0.3.0  
**Стек:** FastAPI + PostgreSQL + psycopg3 + Pydantic v2 + OpenAI API

---

## Структура проекта

```
ВМЕСТЕ/
├── app/                         # Основное приложение
│   ├── main.py                  # FastAPI приложение и эндпоинты
│   ├── db/                      # Слой доступа к БД
│   │   ├── connection.py        # Пул соединений psycopg
│   │   ├── models.py            # Pydantic модели для БД
│   │   └── repositories/        # Repository pattern
│   ├── models/                  # Доменные модели (не БД)
│   └── services/                # Бизнес-логика и LLM агенты
├── config.py                    # Настройки через Pydantic Settings
├── db/init.sql                  # Схема БД
├── scripts/                     # CLI утилиты и демо
├── tests/                       # Тесты (pytest + coverage)
└── docker-compose.yml           # Оркестрация (api, postgres, chroma)
```

---

## Конфигурация (config.py)

**Назначение:** Единый источник настроек приложения и инфраструктуры.

**Ключевые компоненты:**
- `Settings` — Pydantic модель с валидацией переменных окружения
- `get_settings()` — Singleton для доступа к настройкам (LRU cache)

**Переменные окружения:**
- `APP_ENV` — development | production | test
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `OPENAI_MODEL` — модель для LLM (по умолчанию gpt-4.1-mini)

**Методы:**
- `postgres_dsn` — формирует строку подключения к PostgreSQL

---

## Слой доступа к БД (app/db/)

### connection.py

**Назначение:** Управление пулом соединений и выполнение SQL-запросов.

**Ключевые функции:**
- `get_connection()` — контекстный менеджер для получения соединения из пула
- `fetch_all(query, params)` — SELECT с возвратом всех строк (list[DictRow])
- `fetch_one(query, params)` — SELECT одной строки (DictRow | None)
- `execute(query, params)` — INSERT/UPDATE/DELETE без возврата данных
- `fetch_many(query, params_seq)` — batch-запросы

**Пул:** psycopg-pool с `min_size=1, max_size=5`, autocommit=True

### models.py

**Назначение:** Pydantic модели для сериализации/валидации данных БД.

**Модели:**

**Пользователи:**
- `User` — карточка пользователя (user_id, external_id, email, profile_json)
- `UserCreate` — входные данные для создания пользователя

**Сессии:**
- `Session` — сессия диалога (session_id, user_id, mode, status, state_json, started_at, ended_at)
- `SessionCreate` — создание сессии
- `SessionUpdateStatus` — обновление статуса

**Чат:**
- `ChatMessage` — сообщение из chat_history (message_id, session_id, user_id, sender, payload, scores)
- `ChatMessageCreate` — входные данные для создания сообщения

**Память и квиз:**
- `UserMemory` — долговременная память (memory_id, user_id, memory_data)
- `UserMemoryUpsert` — создание/обновление памяти
- `QuizProfile` — снимок квиз-профиля (version, completed, answers)
- `QuizProfileUpdate` — частичное обновление квиза
- `QuizAnswer` — ответ на вопрос (value, confidence, updated_at)
- `QuizAnswerUpdate` — данные для обновления ответа

### repositories/ (Repository Pattern)

#### users.py
**CRUD пользователей:**
- `create_user(UserCreate)` → User
- `get_by_email(str)` → User | None
- `get_by_id(UUID)` → User | None
- `update_profile(user_id, profile_json)` → User

#### sessions.py
**Управление сессиями:**
- `create_session(SessionCreate)` → Session
- `get_active_session(user_id)` → Session | None
- `close_session(session_id, status, ended_at)` → Session
- `update_state(session_id, state_json)` → Session

#### chat_history.py
**История сообщений:**
- `add_message(ChatMessageCreate)` → ChatMessage
- `list_by_session(session_id, limit)` → list[ChatMessage]
- `list_by_user(user_id, limit)` → list[ChatMessage]

#### user_memory.py
**Долговременная память:**
- `get_memory(user_id)` → UserMemory | None
- `upsert_memory(UserMemoryUpsert)` → UserMemory
- `append_conversation_entry(user_id, entry, max_length)` → UserMemory
  - Автоматически добавляет сообщение в conversation_history
  - Ограничивает длину до max_length (по умолчанию 2000)
- `get_quiz_profile(user_id)` → QuizProfile | None
- `upsert_quiz_profile(user_id, QuizProfileUpdate)` → QuizProfile
  - Умное слияние с существующими данными

**Вспомогательные функции:**
- `_ensure_memory_structure()` — гарантирует базовую структуру memory_data
- `_merge_quiz_profile()` — объединяет существующий и новый квиз-профили
- `_build_quiz_answer()` — формирует полный QuizAnswer из QuizAnswerUpdate

#### psychologist_content.py
**Каталог материалов:**
- `list_available(limit)` → list[dict] — выборка активных материалов психолога

---

## API Endpoints (app/main.py)

**Базовые:**
- `GET /health` → HealthResponse — проверка работоспособности
- `POST /entry` → EntryResponse — проверить пользователя по email, создать при отсутствии и вернуть `is_new`, `quiz_completed`

**Пользователи (users):**
- `POST /users` → User — создать или вернуть существующего по email
- `GET /users/email/{email}` → User — получить по email
- `GET /users/{user_id}` → User — получить по UUID
- `PUT /users/{user_id}/profile` → User — обновить profile_json

**Сессии (sessions):**
- `POST /sessions` → Session — создать сессию
- `GET /sessions/{user_id}/active` → Session | None — активная сессия
- `POST /sessions/{session_id}/close` → Session — завершить сессию
- `PATCH /sessions/{session_id}/state` → Session — обновить state_json

**Чат (chat):**
- `POST /sessions/{session_id}/messages` → ChatMessage — записать сообщение + автоматически в user_memory
- `GET /sessions/{session_id}/messages` → list[ChatMessage] — история сессии
- `GET /users/{user_id}/messages` → list[ChatMessage] — история пользователя

**Память (memory):**
- `GET /users/{user_id}/memory` → UserMemory | None — получить memory_data
- `PUT /users/{user_id}/memory` → UserMemory — обновить memory_data

**Квиз:**
- `GET /users/{user_id}/quiz-profile` → QuizProfile | None — получить ответы квиза
- `PUT /users/{user_id}/quiz-profile` → QuizProfile — обновить ответы

**Request/Response модели:**
- `HealthResponse`, `CloseSessionRequest`, `UpdateStateRequest`, `EntryRequest`, `EntryResponse`
- `ChatMessageRequest`, `MemoryRequest`, `ProfileRequest`

---

## Доменные модели (app/models/)

**Назначение:** Pydantic модели для бизнес-логики (не привязаны к схеме БД).

**Модули:**

### user_profile.py
- `UserProfileModel` — структура profile_json для LLM
  - Поля: stress_level, emotional_tone, key_concerns, support_needs, strengths, motivation_trend, tov_style_tag, recommended_focus, risk_flags, summary
  - Типы: StressLevel, MotivationTrend (Literal)

### quiz.py
- `QuizQuestion`, `QuizAnswer`, `QuizResult`
- `QuestionType`, `ChoiceOption`

### recommendation.py
- `ContentCandidate` — кандидат на рекомендацию
- `RecommendationOffer` — оффер с материалами
- `RecommendationReply` — ответ агента рекомендаций

### rag_chat.py
- `RagReference` — ссылка на источник из RAG
- `RagReply` — ответ с контекстом

### dialog_summary.py
- `DialogSummary` — краткое резюме диалога

### therapy.py
- `TherapyReply` — ответ терапевтического агента

### diagnostic.py
- `BodyInsight`, `MindInsight`, `SexInsight`
- `DiagnosticBundle` — комплексная диагностика

### week_plan.py
- `PlanItem`, `WeekPlan` — план на неделю

---

## Сервисы (app/services/)

**Назначение:** Бизнес-логика и интеграция с LLM.

### profile_enrichment.py
**Генерация profile_json через LLM:**
- `ProfileEnrichmentService` — инкапсулирует OpenAI API
  - `generate_profile(quiz_answers, current_profile, extra_context)` → UserProfileModel
  - `_build_messages()` — формирует промпт для LLM
- `enrich_user_profile(user_id, quiz_answers, extra_context)` → UserProfileModel
  - Генерирует профиль и сохраняет в users.profile_json

**Системный промпт:** анализ квиза для создания структурированного профиля

### recommendation_agent.py
**Рекомендации материалов психолога:**
- Анализ профиля пользователя
- Выборка релевантных материалов из psychologist_content
- Формирование офферов

### rag_chat_agent.py
**RAG-чат с контекстом:**
- Поиск релевантных чанков через векторное хранилище
- Генерация ответа с учетом контекста
- Возврат ссылок на источники

### quiz_service.py
**Управление квизом:**
- Формирование вопросов
- Валидация ответов
- Сохранение результатов в user_memory через `run_quiz_for_user`

### app/cli/pipeline_cli.py
**CLI пайплайн:**
- Проверка шага входа (создание/поиск пользователя, статус квиза)
- Запуск интерактивного квиза и запись ответов
- Вывод сводки в текстовом или JSON-формате

### dialog_summary.py
**Саммаризация диалогов:**
- Анализ истории сообщений
- Генерация краткого резюме

### therapy_agent.py
**Терапевтический чат:**
- Поддерживающий диалог с эмпатией
- Учет истории взаимодействий

### diagnostic_agent.py
**Диагностика состояния:**
- Анализ по трем направлениям (body, mind, sex)
- Формирование инсайтов и рекомендаций

### week_plan_agent.py
**Планирование недели:**
- Генерация персонализированных активностей
- Учет приоритетов и возможностей

---

## Скрипты (scripts/)

### chat_cli.py
**Интерактивный чат с LLM:**
- Загружает историю из user_memory
- Формирует промпт с полной историей (до 40 сообщений)
- Отправляет в OpenAI GPT-4.1 mini
- Автоматически сохраняет в chat_history и user_memory

**Системный промпт:** эмпатичный ассистент с доступом к истории разговоров

### quiz_demo.py
**Демонстрация семейного квиза:**
- Создает пользователя
- Задает 5 вопросов (family_structure, children_ages, primary_concern, support_preferred, previous_experience)
- Сохраняет через PUT /users/{user_id}/quiz-profile

### chroma_bootstrap.py
**Инициализация векторного хранилища:**
- Настройка Chroma коллекций
- Загрузка начальных данных

### wipe_database.py / wipe_chroma.py
**Утилиты для очистки данных:**
- Полная очистка PostgreSQL
- Очистка Chroma векторов

---

## Тесты (tests/)

### conftest.py
**Фикстуры для pytest:**
- Настройка тестовой БД
- Mock клиенты

### test_api.py
**API тесты:**
- Покрытие всех эндпоинтов
- Валидация request/response

### test_database.py
**Тесты репозиториев:**
- CRUD операции
- Транзакции

### test_core.py
**Core функциональность:**
- Конфигурация
- Пул соединений

**Coverage:** ~88% (по последним коммитам)

---

## Docker и запуск

### docker-compose.yml
**Сервисы:**
- `api` — FastAPI (порт 8000)
- `postgres` — PostgreSQL 16 (порт 5432)
- `chroma` — векторное хранилище (порт 8001)

**Volumes:**
- `postgres-data` — данные БД
- `chroma-data` — векторы

### Dockerfile
**Образ API:**
- Python 3.11+
- pip install -r requirements.txt
- Запуск через uvicorn

---

## Ключевые особенности

**Автоматическое сохранение в память:**
При `POST /sessions/{session_id}/messages`:
1. Сообщение → chat_history
2. Автоматически → user_memory.conversation_history через `append_conversation_entry()`
3. История обрезается до max_length=2000

**Умное слияние квиз-профилей:**
`upsert_quiz_profile()` мерджит частичные обновления с существующими данными, сохраняя целостность.

**Версионирование квиза:**
QuizProfile.version позволяет обновлять схему квиза без потери данных.

**Системы оценок:**
chat_history хранит expert_score и user_score (1-5) с валидацией на уровне БД.

**LLM интеграция:**
- OpenAI GPT-4.1 mini для тестирования
- Structured Outputs (Pydantic response_format)
- Система промптов для разных режимов (intake/consultation/support)

---

**Версия документа:** 2025-11-13  
**Последнее обновление:** Анализ актуального состояния проекта
