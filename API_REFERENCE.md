# API Reference «Вместе»

Единый справочник по REST API backend-сервиса. Документ синхронизирован с текущей реализацией `app/main.py` (FastAPI v0.3.0).  
Базовый URL локального окружения: `http://localhost:8000`.

- Swagger UI: `GET /docs`  
- Redoc: `GET /redoc`  
- OpenAPI JSON: `GET /openapi.json`

## Сводка эндпоинтов

| Метод | URL | Назначение | Группа |
| --- | --- | --- | --- |
| GET | /health | Проверка статуса сервиса | service |
| POST | /entry | Поиск/создание пользователя по email | entry |
| GET | /quiz/questions | Список вопросов квиза | quiz |
| POST | /quiz/submit | Сохранение ответов квиза | quiz |
| POST | /users | Создать пользователя | users |
| GET | /users/email/{email} | Получить по email | users |
| GET | /users/{user_id} | Получить по UUID | users |
| PUT | /users/{user_id}/profile | Обновить profile_json | users |
| POST | /users/{user_id}/profile/enrich | Запуск LLM-обогащения профиля | users |
| POST | /users/{user_id}/diagnostic/run | Диагностика + рекомендации контента | diagnostic |
| POST | /users/{user_id}/week-plan/run | Планировщик недели | planning |
| POST | /sessions | Создать сессию | sessions |
| GET | /sessions/{user_id}/active | Активная сессия пользователя | sessions |
| POST | /sessions/{session_id}/close | Закрыть сессию | sessions |
| PATCH | /sessions/{session_id}/state | Обновить state_json | sessions |
| POST | /sessions/{session_id}/messages | Добавить сообщение | chat |
| GET | /sessions/{session_id}/messages | История сессии | chat |
| GET | /users/{user_id}/messages | История пользователя | chat |
| GET | /users/{user_id}/memory | Прочитать память | memory |
| PUT | /users/{user_id}/memory | Создать/обновить память | memory |
| GET | /users/{user_id}/quiz-profile | Прочитать квиз-профиль | memory |
| PUT | /users/{user_id}/quiz-profile | Обновить квиз-профиль | memory |

Ниже — подробные карточки маршрутов.

---

## 1. Service & Entry

### GET /health
- **Назначение:** Быстрый health-check.  
- **Ответ:** `200 OK`, `{"status":"ok"}` (`HealthResponse`).  
- **Ошибки:** нет.

### POST /entry
- **Назначение:** Проверить пользователя по email и вернуть `is_new`.  
- **Request:**  
  ```json
  { "email": "user@example.com" }
  ```  
- **Response:** `200 OK`, модель `EntryResponse`  
  ```json
  {
    "user": { ...User... },
    "is_new": false,
    "quiz_completed": true
  }
  ```  
- **Ошибки:** 422 (некорректный email).

---

## 2. Quiz

### GET /quiz/questions
- Возвращает список `QuizQuestion` (актуальная версия; сейчас без параметров).

### POST /quiz/submit
- **Назначение:** Валидировать и сохранить ответы в `user_memory`.  
- **Request (QuizSubmitRequest):**
  ```json
  {
    "user_id": "uuid",
    "answers": [
      {"question_id": "age", "value": "30"}
    ],
    "force": false,
    "version": "1.0"
  }
  ```
- **Поведение:**
  - Если квиз уже завершён и `force=false`, возвращается кэш.
  - Валидация выполняется через `quiz_service.validate_answers`.  
- **Response (QuizSubmitResponse):** флаги `was_updated`, `completed`, `version`, `completed_at`, слепок ответов.  
- **Ошибки:**  
  - `404` — пользователь не найден.  
  - `400` — пустой список ответов или ошибки валидации.

---

## 3. Users & Profile

### POST /users
- Создаёт пользователя или возвращает существующего (по email). `201 Created`.

### GET /users/email/{email}
- Возвращает пользователя по email. `404`, если нет.

### GET /users/{user_id}
- Возвращает пользователя по UUID. `404`, если нет.

### PUT /users/{user_id}/profile
- **Request:** `{"profile_json": {...}}`.  
- **Response:** обновлённый `User`.  
- **Ошибки:** `404`, если пользователь не найден.

### POST /users/{user_id}/profile/enrich
- **Назначение:** Запустить `ensure_profile_for_user`.  
- **Request:** `{"force": false, "extra_context": "..."}`.  
- **Response:**  
  ```json
  {
    "enriched": true,
    "profile": {...}
  }
  ```  
- **Ошибки:** `404` (нет пользователя), `400` (нет данных для обогащения, ошибка валидации).

---

## 4. Diagnostic & Planning

### POST /users/{user_id}/diagnostic/run
- **Назначение:** Запускает `run_diagnostic_with_recommendations`, параллельно выполняет диагностику и подбор контента, сохраняет результат в память.
- **Request:** `{"force": false}`.
- **Response:**
  ```json
  {
    "bundle": {...DiagnosticBundle...},
    "from_cache": false,
    "recommendations": [...BlockRecommendation...],
    "recommendations_from_cache": false
  }
  ```
- **Ошибки:** `404` (нет пользователя), `400` (у пользователя пустой профиль).

### POST /users/{user_id}/week-plan/run
- **Назначение:** Генерация недельного плана через `run_week_plan_with_cache` на основе полного контекста (профиль, квиз, диагностика, теги).
- **Request:**
  ```json
  {
    "selected_tags": ["стресс", "тревога"],  // опционально, берутся из диагностики если не указаны
    "force": false
  }
  ```
- **Response:**
  ```json
  {
    "plan": {...WeekPlan...},
    "from_cache": false,
    "tags": ["стресс","тревога"]  // фактически использованные теги
  }
  ```
- **Ошибки:** `404` (нет пользователя), `400` (диагностика ещё не выполнена или другие ошибки валидации).

---

## 5. Sessions & State

### POST /sessions
- Создаёт запись `Session` (см. `SessionCreate`). `201 Created`.

### GET /sessions/{user_id}/active
- Возвращает активную сессию пользователя или `null`.

### POST /sessions/{session_id}/close
- **Request:** `{"status": "completed", "ended_at": "2025-11-19T12:00:00Z"}`.  
- **Ошибки:** `404`, если сессия не найдена.

### PATCH /sessions/{session_id}/state
- **Request:** `{"state_json": {...}}`.  
- **Ошибки:** `404`, если сессия не найдена.

---

## 6. Chat History

### POST /sessions/{session_id}/messages
- **Назначение:** Записать сообщение в `chat_history` и автоматически добавить его в `user_memory.conversation_history`.  
- **Request (ChatMessageRequest):**
  ```json
  {
    "user_id": "uuid",
    "sender": "user",
    "message_type": "text",
    "payload": {"text": "Привет"},
    "request_timestamp": "2025-11-19T10:00:00Z"
  }
  ```
- **Response:** сохранённый `ChatMessage`.  
- **Ошибки:** 422 (некорректные поля) или ошибки репозитория.

### GET /sessions/{session_id}/messages
- Возвращает список `ChatMessage` (по умолчанию `limit=100`, query-параметр `limit` опционален).

### GET /users/{user_id}/messages
- Возвращает сообщения пользователя через все сессии (`limit` по умолчанию 200).

---

## 7. Memory & Quiz Profile

### GET /users/{user_id}/memory
- Возвращает `UserMemory` или `null`.

### PUT /users/{user_id}/memory
- **Request:** `{"memory_data": {...}}`.  
- **Response:** созданная/обновлённая память (`UserMemory`).  
- **Ошибки:** ошибки валидации данных памяти (422).

### GET /users/{user_id}/quiz-profile
- Возвращает `QuizProfile` или `null`.

### PUT /users/{user_id}/quiz-profile
- **Request:** `QuizProfileUpdate` (частичное обновление).  
- **Response:** новый `QuizProfile`.

---

## 8. Примеры `curl`

```bash
# Health
curl http://localhost:8000/health

# Entry
curl -X POST http://localhost:8000/entry \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@vmeste.io"}'

# Quiz submit
curl -X POST http://localhost:8000/quiz/submit \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<uuid>","answers":[{"question_id":"age","value":"30"}]}'

# Week plan (теги опциональны)
curl -X POST http://localhost:8000/users/<uuid>/week-plan/run \
  -H "Content-Type: application/json" \
  -d '{"selected_tags":["стресс","тревога"]}'

# Week plan без тегов (берутся из диагностики)
curl -X POST http://localhost:8000/users/<uuid>/week-plan/run \
  -H "Content-Type: application/json" \
  -d '{}'
```

Документ обновляется при любом изменении FastAPI-маршрутов (истина — `app/main.py`).
