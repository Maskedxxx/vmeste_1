# «Вместе» — backend v0

Проект создаёт основу LLM-сервиса для персонализированных рекомендаций психологического контента. Текущая цель — поднять минимальный API, контейнеры и базу данных для дальнейшего развития workflow «сбор → понимание → рекомендация».

## Стек первой итерации
- FastAPI — входная точка и оркестрация запросов
- LangChain + LangGraph — реализация многошагового диалога (будет подключено далее)
- Chroma — локальное векторное хранилище в контейнере
- PostgreSQL — транзакционная база для пользователей, сессий и истории (развёрнута в docker-compose)
- Redis — будет добавлен на следующем этапе
- YandexGPT — облачная LLM, интеграция планируется
- Langfuse — наблюдаемость и трассировка цепочек

## Быстрый старт
1. Установите зависимости: `pip install -r requirements.txt`
2. Запустите приложение: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. Проверьте статус: `curl http://localhost:8000/health` → ожидается `{"status":"ok"}`

### Запуск в контейнере
1. Создайте файл окружения: `cp .env.example .env`
2. Поднимите сервисы: `docker compose up --build`
3. API станет доступным по `http://localhost:8000`, Chroma — на `http://localhost:8001`, PostgreSQL — на `localhost:5432`
4. Для остановки исполните `docker compose down` (данные БД сохраняются в named-volume `postgres_data`)

### Структура БД (v0)
- `sources` — реестр исходных материалов (тип, ссылка, метаданные, soft delete)
- `documents` — тексты после транскрибации, связаны с источниками
- `content_chunks` — рабочие фрагменты для RAG с темами, TOV и метаданными
- `chunk_embeddings_meta` — связь чанков с коллекциями Chroma и статус синхронизации
- `psychologist_content` — каталог платных материалов (описание, цена, теги)
- `style_examples` — эталонные Q/A для поддержания тона общения
- `users` — карточка пользователя и профиль intake (JSONB)
- `sessions` — сессии диалога: режим (`intake`, `consultation`, `support`), статус, состояние LangGraph
- `chat_history` — все сообщения в рамках сессий, с метками качества (`expert_score`, `user_score`)
- `user_memory` — агрегированная долговременная память пользователя (ключ-значение в JSONB)

Инициализационный SQL находится в `db/init.sql` и выполняется автоматически при первом старте контейнера PostgreSQL.

### Проверка слоя доступа к БД
1. `pip install -r requirements.txt`
2. `docker compose up --build -d`
3. `python -m app.db.connection`
4. `python -m app.db.repositories.users`
5. `python -m app.db.repositories.sessions`
6. `python -m app.db.repositories.chat_history`
7. `python -m app.db.repositories.user_memory`
8. `docker compose down`

### CLI-демо
- Убедитесь, что API запущен (`uvicorn app.main:app --reload` или `docker compose up`)
- `python scripts/chat_cli.py` — интерактивный чат с реальной LLM (нужен `OPENAI_API_KEY`, опционально `OPENAI_MODEL`)
- После скриптов можно посмотреть записи в `chat_history` и `user_memory`

### API (v0)
- `POST /users` — создать пользователя или вернуть существующего по email
- `GET /users/email/{email}` — получить пользователя по email
- `GET /users/{user_id}` — получить пользователя по внутреннему идентификатору
- `PUT /users/{user_id}/profile` — обновить профиль
- `POST /sessions` — создать сессию
- `GET /sessions/{user_id}/active` — получить активную сессию
- `POST /sessions/{session_id}/close` — завершить сессию
- `PATCH /sessions/{session_id}/state` — обновить state графа
- `POST /sessions/{session_id}/messages` — записать сообщение
- `GET /sessions/{session_id}/messages` — история сессии
- `GET /users/{user_id}/messages` — история по пользователю
- `GET /users/{user_id}/memory` — получить память
- `PUT /users/{user_id}/memory` — обновить память

## Структура репозитория
- `app/main.py` — приложение FastAPI, `/health` и базовые CRUD эндпоинты
- `requirements.txt` — минимальный набор зависимостей
- `docker-compose.yml` — сервисы API, Chroma и PostgreSQL
- `Dockerfile` — сборка контейнера API
- `.env.example` — шаблон переменных окружения
- `db/init.sql` — схема таблиц пользователей и контента в PostgreSQL
- `Legacy/` — исходные материалы проекта (не попадает в репозиторий)

Дальше планируется реализация LangGraph workflow, расширение схемы данными контента и интеграция с YandexGPT.
