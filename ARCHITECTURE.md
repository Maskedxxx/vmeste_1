# Архитектура приложения «Вместе»

## Обзор

LLM-сервис для персонализированной психологической поддержки на базе FastAPI с PostgreSQL, реализующий паттерн Repository для доступа к данным.

**Версия:** 0.4.0
**Стек:** FastAPI + PostgreSQL + psycopg3 + Pydantic v2 + OpenAI API + Chroma (RAG)

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
├── bot/                         # Внешние клиенты (Telegram и т.д.)
│   └── telegram_bot.py          # Aiogram-бот для теста входа
├── config.py                    # Настройки через Pydantic Settings
├── db/init.sql                  # Схема БД
├── scripts/                     # Утилиты и вспомогательные скрипты
├── tests/                       # Тесты (pytest + coverage)
└── docker-compose.yml           # Оркестрация (api, postgres, chroma, bot)
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
- `TELEGRAM_BOT_TOKEN` — токен бота для Aiogram
- `VMESTE_API_BASE` — базовый URL REST API для внешних клиентов (бот)

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
- `get_diagnostic_recommendations(user_id)` → list[dict] | None — получить кэшированные рекомендации
- `upsert_diagnostic_recommendations(user_id, recommendations)` → list[dict] — сохранить рекомендации диагностики

**Вспомогательные функции:**
- `_ensure_memory_structure()` — гарантирует базовую структуру memory_data
- `_merge_quiz_profile()` — объединяет существующий и новый квиз-профили
- `_build_quiz_answer()` — формирует полный QuizAnswer из QuizAnswerUpdate

#### psychologist_content.py
**Каталог материалов:**
- `list_available(limit)` → list[dict] — выборка активных материалов психолога (включая url)
- `get_by_doc_id(doc_id)` → PsychologistContent | None — получить по ID документа
- `create(payload)` → PsychologistContent — создать запись каталога

#### sources.py
**Провайдеры контента (откуда загружен материал):**
- `get_by_type(source_type)` → Source | None — найти провайдер по типу (manual, yandex_disk и т.д.)
- `create(payload)` → Source — создать нового провайдера

#### documents.py
**Исходные документы:**
- `exists_by_slug(slug)` → bool — проверка существования по slug
- `get_by_slug(slug)` → Document | None — получить документ по slug
- `create(payload)` → Document — создать документ (slug, title, raw_text)

#### content_chunks.py
**Чанки контента для RAG:**
- `create_batch(chunks)` → list[ContentChunk] — массовое создание чанков
- `get_by_doc_id(doc_id)` → list[ContentChunk] — все чанки документа

#### chunk_embeddings_meta.py
**Метаданные эмбеддингов:**
- `create_batch(metas)` → list[ChunkEmbeddingMeta] — массовое создание метаданных
- Связывает chunk_id с chroma_id в ChromaDB

---

## API Endpoints

Полное описание API см. в **README.md** раздел "Использование бота" или Swagger UI (`/docs`).

Краткий список:
- `GET /health` — проверка работоспособности
- `POST /entry` — авторизация по email
- `POST /users`, `GET /users/{id}` — управление пользователями
- `POST /sessions`, `GET /sessions/{user_id}/active` — управление сессиями
- `POST /chat` — RAG-чат по темам (body/mind/sex)
- `POST /users/{id}/diagnostic/run` — диагностика
- `POST /users/{id}/week-plan/run` — план на 7 дней
- `GET /quiz/questions`, `POST /quiz/submit` — квиз

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
- `ContentCandidate` — кандидат на рекомендацию (content_id, title, summary, url, topic, content_type, tags)
- `RecommendationOffer` — оффер с материалами
- `RecommendationReply` — ответ агента рекомендаций
- `BlockRecommendation` — рекомендация для диагностического блока (body/mind/sex)

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
- `PlanItem` — день плана (day, title, goal, instructions, tags, focus_area)
- `WeekPlan` — план на 7 дней

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
- Формирование персонализированных офферов
- `generate_block_recommendations()` — генерация рекомендаций для диагностических блоков (body/mind/sex)

### rag_chat_agent.py
**RAG-чат с контекстом:**
- Поиск релевантных чанков через векторное хранилище
- Генерация ответа с учетом контекста
- Возврат ссылок на источники

### diagnostic_agent.py
**Диагностика состояния:**
- Анализ по трем направлениям (body, mind, sex)
- Формирование инсайтов и тегов
- Сохранение результатов в user_memory (`diagnostic_bundle`) с поддержкой force-режима

### diagnostic_workflow.py
**Оркестратор диагностики и рекомендаций:**
- Параллельный запуск диагностики и подбора контента через ThreadPoolExecutor
- Кэширование результатов диагностики и рекомендаций раздельно
- `run_diagnostic_with_recommendations()` — возвращает (bundle, диагностика_из_кэша, рекомендации, рекомендации_из_кэша)

### quiz_service.py
**Управление квизом:**
- Формирование вопросов
- Валидация ответов
- Сохранение результатов в user_memory через `run_quiz_for_user`

### dialog_summary.py
**Саммаризация диалогов:**
- Анализ истории сообщений
- Генерация краткого резюме

### therapy_agent.py
**Терапевтический чат:**
- Поддерживающий диалог с эмпатией
- Учет истории взаимодействий

### week_plan_agent.py
**Планирование недели:**
- Генерация 7-дневного плана на основе полного контекста пользователя (профиль, квиз, диагностика, теги)
- Теги опциональны — если не указаны, извлекаются из диагностики автоматически
- План содержит самостоятельные практики без привязки к платному контенту
- Умное кэширование на основе хэша контекста (context_hash)
- `run_week_plan_with_cache()` — возвращает (план, from_cache, использованные_теги)

### bot/telegram_bot.py
**Telegram-клиент (Aiogram):**
- Команды `/start` + обработка email
- Авторизация через `/entry`, прохождение квиза, автоматическое обогащение профиля
- Диагностика: пошаговый выбор тегов из агентского ответа
- Кнопка «Статус» показывает прогресс пользователя
- Запускается отдельным процессом (`python -m bot.telegram_bot`), не входит в docker-compose
- Зависимости ставятся из `requirements-bot.txt`

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
- Запуск через uvicorn (для сервиса `api`), бот использует тот же образ с командой `python -m bot.telegram_bot`

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

**Версия документа:** 2026-01-14
**Последнее обновление:** Добавлены репозитории content pipeline (sources, documents, content_chunks, chunk_embeddings_meta), убраны дубли API
