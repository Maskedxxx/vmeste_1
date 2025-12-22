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

### Запуск в контейнере (development)
1. Создайте файл окружения: `cp .env.example .env`
2. Поднимите сервисы: `docker compose up --build`
3. API станет доступным по `http://localhost:8000`, Chroma — на `http://localhost:8001`, PostgreSQL — на `localhost:5432`
4. Для остановки исполните `docker compose down` (данные БД сохраняются в named-volume `postgres_data`)

### Production деплой
Для production используется отдельный compose-файл без контейнера PostgreSQL (используется внешняя БД сервера).

```bash
# 1. Клонировать репозиторий
git clone https://github.com/myosminozhka-ru/VmesteMentor.git
cd VmesteMentor

# 2. Настроить окружение
cp .env.example .env
# Отредактировать .env:
#   APP_ENV=production
#   POSTGRES_HOST=<адрес_сервера_БД>
#   POSTGRES_PASSWORD=<надёжный_пароль>
#   API_PORT=<свободный_порт>        # если 8000 занят
#   CHROMA_PORT=<свободный_порт>     # если 8001 занят
#   OPENAI_API_KEY=sk-...

# 3. Инициализировать БД (выполнить db/init.sql на сервере PostgreSQL)
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -f db/init.sql

# 4. Запустить сервисы
docker compose -f docker-compose.prod.yml up --build -d

# 5. Проверить
curl http://127.0.0.1:8000/health  # {"status":"ok"}
```

**Особенности production-конфига:**
- Порты доступны только на `127.0.0.1` (не публично) — доступ через reverse proxy (nginx/traefik)
- PostgreSQL контейнер отсутствует — используется внешняя БД
- Healthcheck для мониторинга
- `restart: unless-stopped` для автоперезапуска

### Подготовка окружения
```bash
docker compose up postgres chroma -d    # инфраструктура
export OPENAI_API_KEY=sk-...            # ключ OpenAI
export VMESTE_DEMO_USER_ID=<uuid>       # пользователь для демо-команд
```
Далее пройдите CLI-пайплайн (квиз → профиль → диагностика → план), чтобы у пользователя появились все данные.

### БД (11 таблиц)
**Пользователи:** users, sessions, chat_history, user_memory
**Контент:** sources, documents, content_chunks, chunk_embeddings_meta, embedding_index_state, psychologist_content, style_examples

Схема: `db/init.sql` (выполняется автоматически в Docker)

### Пайплайн (CLI)
```bash
python -m app.cli.pipeline_cli --email demo@vmeste.io --quiz
python -m app.cli.pipeline_cli --email demo@vmeste.io --profile
python -m app.cli.pipeline_cli --email demo@vmeste.io --diagnostic
# --plan-tags опциональный, теги берутся из диагностики если не указаны
python -m app.cli.pipeline_cli --email demo@vmeste.io --week-plan --plan-tags "стресс, тревога"
# Повторно с форсом:
python -m app.cli.pipeline_cli --email demo@vmeste.io \
  --quiz --force-quiz \
  --profile --force-profile \
  --diagnostic --force-diagnostic \
  --week-plan --plan-tags "стресс, тревога" --force-week-plan
```

### Демо LLM-сервисов
```bash
export VMESTE_DEMO_USER_ID=469a0f1d-01de-4340-8e8d-e5897eb43d52
python -m app.services.profile_enrichment
python -m app.services.recommendation_agent
python -m app.services.dialog_summary
python -m app.services.therapy_agent
python -m app.services.diagnostic_agent
python -m app.services.week_plan_agent
```

### Минимальный сценарий через API
```bash
curl -X POST http://localhost:8000/entry -H "Content-Type: application/json" -d '{"email":"demo@vmeste.io"}'
curl http://localhost:8000/quiz/questions
curl -X POST http://localhost:8000/quiz/submit -H "Content-Type: application/json" -d '{"user_id":"<uuid>", "answers":[{"question_id":"age","value":"30"}, ...]}'
curl -X POST http://localhost:8000/users/<uuid>/profile/enrich -H "Content-Type: application/json" -d '{}'
curl -X POST http://localhost:8000/users/<uuid>/diagnostic/run -H "Content-Type: application/json" -d '{}'
# selected_tags опциональный, если не указан — берутся теги из диагностики
curl -X POST http://localhost:8000/users/<uuid>/week-plan/run -H "Content-Type: application/json" -d '{"selected_tags":["стресс","усталость"]}'
```

## Telegram-бот (тест входа)
- Настройте `.env`: `TELEGRAM_BOT_TOKEN=<token>`, `VMESTE_API_BASE`.
- Установите зависимости бота (дополнительно к основным):
  ```bash
  pip install -r requirements-bot.txt
  ```
- Запустите API (`uvicorn app.main:app --reload` или `docker compose up`), затем:
  ```bash
  python -m bot.telegram_bot
  ```
- Бот (Aiogram) обрабатывает `/start`, просит email и вызывает `/entry`, показывает `is_new`, `quiz_completed`, `user_id`.
- Доступные действия: прохождение квиза, запуск диагностики, просмотр статуса.

### API (21 эндпоинт)
**Entry / Users**
- `POST /entry`
- `POST /users`, `GET /users/email/{email}`, `GET /users/{user_id}`
- `PUT /users/{user_id}/profile`, `POST /users/{user_id}/profile/enrich`

**Quiz**
- `GET /quiz/questions`, `POST /quiz/submit`
- `GET /users/{user_id}/quiz-profile`, `PUT /users/{user_id}/quiz-profile`

**Diagnostic & Planning**
- `POST /users/{user_id}/diagnostic/run` — диагностика + персонализированные рекомендации контента
- `POST /users/{user_id}/week-plan/run`

**Sessions / Chat**
- `POST /sessions`, `GET /sessions/{user_id}/active`
- `POST /sessions/{session_id}/close`, `PATCH /sessions/{session_id}/state`
- `POST /sessions/{session_id}/messages`, `GET /sessions/{session_id}/messages`
- `GET /users/{user_id}/messages`

**Memory**
- `GET /users/{user_id}/memory`, `PUT /users/{user_id}/memory`

## Структура
```
app/
├── main.py               # FastAPI эндпоинты
├── cli/
│   └── pipeline_cli.py   # entry → quiz → profile → diagnostic → plan
├── models/
│   ├── user_profile.py
│   ├── diagnostic.py
│   ├── week_plan.py
│   ├── recommendation.py
│   ├── dialog_summary.py
│   ├── therapy.py
│   └── quiz.py
├── services/
│   ├── profile_enrichment.py
│   ├── diagnostic_agent.py
│   ├── diagnostic_workflow.py
│   ├── week_plan_agent.py
│   ├── recommendation_agent.py
│   ├── therapy_agent.py
│   ├── rag_chat_agent.py
│   └── quiz_service.py
└── db/
    ├── models.py        # Схема БД
    ├── connection.py
    └── repositories/    # CRUD операции
bot/
└── telegram_bot.py       # Telegram-клиент для тестирования
```

**Конфигурация:** config.py, .env, docker-compose.yml
**БД:** db/init.sql
