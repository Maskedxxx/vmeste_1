# Тесты проекта «Вместе»

## Структура

```
tests/
├── conftest.py          # Фикстуры (test_db, client, моки)
├── test_core.py         # Unit тесты (5 тестов)
├── test_database.py     # Integration с БД (5 тестов)
└── test_api.py          # API endpoints (5 тестов)
```

**Итого:** 15 тестов, покрытие ~70%

---

## Быстрый старт

### 1. Установить зависимости

```bash
pip install -r requirements-dev.txt
```

### 2. Поднять тестовую БД

```bash
docker compose -f docker-compose.test.yml up -d
```

Тестовая БД запустится на порту **5433** (чтобы не конфликтовать с production на 5432).

### 3. Запустить тесты

```bash
# Все тесты
pytest

# С coverage отчётом
pytest --cov=app --cov-report=html

# Только unit тесты (быстро, без БД)
pytest -m unit

# Только integration тесты
pytest -m integration

# Только API тесты
pytest -m api
```

### 4. Посмотреть coverage

```bash
open htmlcov/index.html  # macOS
```

### 5. Остановить тестовую БД

```bash
docker compose -f docker-compose.test.yml down
```

---

## Категории тестов

### Unit тесты (test_core.py)
- **Не требуют БД**, используют моки
- Очень быстрые (~2-3 сек)
- Тестируют изолированную логику

**Что покрывают:**
- Pydantic валидация (EmailStr, scores 1-5)
- Бизнес-логика user_memory (_merge_quiz_profile, обрезка истории)
- Утилиты (_ensure_memory_structure)

### Integration тесты (test_database.py)
- **Требуют реальную PostgreSQL**
- Медленнее (~10-15 сек)
- Тестируют работу с БД

**Что покрывают:**
- CRUD операции репозиториев
- Foreign keys и constraints
- JSONB операции (upsert, массивы)

### API тесты (test_api.py)
- **Требуют БД + TestClient**
- E2E тесты через HTTP
- Самые медленные (~15-20 сек)

**Что покрывают:**
- Все эндпоинты FastAPI
- Идемпотентность (POST /users)
- Синхронизация chat_history с user_memory
- Мердж квиза

---

## Критичные проверки

### 1. Email уникальность
```python
# test_database.py::test_email_unique_constraint
# Проверяет UNIQUE constraint на email
```

### 2. Двойная запись сообщений
```python
# test_api.py::test_post_message_dual_write
# Сообщение попадает и в chat_history И в user_memory
```

### 3. Мердж квиза
```python
# test_core.py::test_merge_quiz_profile
# Новые ответы добавляются, существующие обновляются
```

### 4. Обрезка истории
```python
# test_core.py::test_conversation_history_limit
# История не превышает 2000 сообщений
```

### 5. Идемпотентность создания пользователя
```python
# test_api.py::test_create_user_idempotent
# POST /users дважды возвращает одного пользователя
```

---

## Фикстуры (conftest.py)

### Для всех тестов
- `test_settings` — настройки для test БД
- `test_db_dsn` — DSN подключения
- `db_connection` — соединение с БД
- `clean_tables` — автоматически очищает таблицы (autouse)

### Для API тестов
- `client` — TestClient с test БД
- `sample_user` — создаёт тестового пользователя
- `sample_session` — создаёт тестовую сессию

### Для unit тестов
- `mock_fetch_one` — мокает fetch_one
- `mock_fetch_all` — мокает fetch_all
- `mock_execute` — мокает execute

---

## Целевые метрики

- **Общее покрытие:** ~70%
- **Репозитории:** 85%+
- **API endpoints:** 80%+
- **Models:** 90%+

---

## Troubleshooting

### Тесты падают с ошибкой подключения к БД

Проверьте что тестовая БД запущена:
```bash
docker compose -f docker-compose.test.yml ps
```

Если контейнер не запущен:
```bash
docker compose -f docker-compose.test.yml up -d
docker compose -f docker-compose.test.yml logs test-postgres
```

### Тесты проходят но покрытие низкое

Добавьте `--cov-report=term-missing` чтобы увидеть непокрытые строки:
```bash
pytest --cov=app --cov-report=term-missing
```

### Тест упал с UniqueViolation

Фикстура `clean_tables` не сработала. Проверьте что она импортирована в conftest.py и помечена `autouse=True`.

Можно очистить БД вручную:
```bash
docker compose -f docker-compose.test.yml down -v
docker compose -f docker-compose.test.yml up -d
```

---

## Добавление новых тестов

### Unit тест
```python
@pytest.mark.unit
def test_my_function():
    # Используйте моки для изоляции
    result = my_function()
    assert result == expected
```

### Integration тест
```python
@pytest.mark.integration
def test_my_repository(db_connection):
    # Используйте реальную БД
    data = repository.create(...)
    assert data.id is not None
```

### API тест
```python
@pytest.mark.api
def test_my_endpoint(client):
    # Используйте TestClient
    response = client.get("/my-endpoint")
    assert response.status_code == 200
```

---

## CI/CD (будущее)

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    docker compose -f docker-compose.test.yml up -d
    pytest --cov=app --cov-fail-under=70
    docker compose -f docker-compose.test.yml down
```
