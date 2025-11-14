# «Вместе» — backend v0.4

LLM-сервис для персонализированной психологической поддержки. Реализовано: REST API, LLM-агенты (профиль, рекомендации, терапия, саммари), долговременная память, векторное хранилище.

## Стек
- **FastAPI** — REST API
- **PostgreSQL** — транзакционные данные (11 таблиц)
- **Chroma** — векторное хранилище (в контейнере)
- **OpenAI** — LLM для тестирования (gpt-4.1-mini)
- **Pydantic v2** — валидация и structured outputs
- **Docker Compose** — оркестрация контейнеров

*Планируется:* LangGraph, YandexGPT, Redis, Langfuse

## Быстрый старт
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...  # для LLM-сервисов
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health  # {"status":"ok"}
```

### Запуск в контейнере
1. Создайте файл окружения: `cp .env.example .env`
2. Поднимите сервисы: `docker compose up --build`
3. API станет доступным по `http://localhost:8000`, Chroma — на `http://localhost:8001`, PostgreSQL — на `localhost:5432`
4. Для остановки исполните `docker compose down` (данные БД сохраняются в named-volume `postgres_data`)

### БД (11 таблиц)
**Пользователи:** users, sessions, chat_history, user_memory
**Контент:** sources, documents, content_chunks, chunk_embeddings_meta, embedding_index_state, psychologist_content, style_examples

Схема: `db/init.sql` (выполняется автоматически в Docker)

### Демо и проверка
```bash
# Репозитории
docker compose up postgres -d
python -m app.db.repositories.users

# LLM-сервисы (требуется OPENAI_API_KEY)
export VMESTE_DEMO_USER_ID=469a0f1d-01de-4340-8e8d-e5897eb43d52
python -m app.services.profile_enrichment    # профиль из квиза
python -m app.services.recommendation_agent  # персонализация контента
python -m app.services.dialog_summary        # саммари диалога
python -m app.services.therapy_agent         # терапевтический ответ

# Пайплайн входа/квиза (CLI)
python -m app.cli.pipeline_cli --email demo@vmeste.io
python -m app.cli.pipeline_cli --email demo@vmeste.io --quiz  # пройти квиз и сохранить
python -m app.cli.pipeline_cli --email demo@vmeste.io --profile  # проверить профиль
python -m app.cli.pipeline_cli --email demo@vmeste.io --quiz --profile --force-profile
```

### API (12 эндпоинтов)
- `POST /entry` — проверяет пользователя по email, создаёт нового при отсутствии (отдаёт `is_new` и `quiz_completed`)
- `POST /users` — создать пользователя или вернуть существующего по email
- `GET /users/email/{email}` — получить пользователя по email
- `GET /users/{user_id}` — получить пользователя по внутреннему идентификатору
- `PUT /users/{user_id}/profile` — обновить профиль
- `POST /users/{user_id}/profile/enrich` — запустить LLM-обогащение profile_json (force-перезапись опциональна)
- `POST /sessions` — создать сессию
- `GET /sessions/{user_id}/active` — получить активную сессию
- `POST /sessions/{session_id}/close` — завершить сессию
- `PATCH /sessions/{session_id}/state` — обновить state графа
- `POST /sessions/{session_id}/messages` — записать сообщение
- `GET /sessions/{session_id}/messages` — история сессии
- `GET /users/{user_id}/messages` — история по пользователю
- `GET /users/{user_id}/memory` — получить память
- `PUT /users/{user_id}/memory` — обновить память
- `GET /users/{user_id}/quiz-profile` — получить ответы квиза
- `PUT /users/{user_id}/quiz-profile` — записать/обновить ответы квиза

## Структура
```
app/
├── main.py              # FastAPI эндпоинты
├── cli/                 # CLI-инструменты пайплайна
│   └── pipeline_cli.py
├── models/              # Pydantic схемы для LLM
│   ├── user_profile.py
│   ├── recommendation.py
│   ├── dialog_summary.py
│   └── therapy.py
├── services/            # LLM-сервисы
│   ├── profile_enrichment.py
│   ├── recommendation_agent.py
│   ├── dialog_summary.py
│   ├── therapy_agent.py
│   └── quiz_service.py
└── db/
    ├── models.py        # Схема БД
    ├── connection.py
    └── repositories/    # CRUD операции
```

**Конфигурация:** config.py, .env, docker-compose.yml
**БД:** db/init.sql
