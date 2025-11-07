# tests/conftest.py
"""Глобальные фикстуры для всех тестов."""

import os
from typing import Any, Generator
from uuid import uuid4

# ВАЖНО: Устанавливаем переменные окружения ДО импорта app модулей
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5433"
os.environ["POSTGRES_DB"] = "test_vmeste"
os.environ["POSTGRES_USER"] = "test_user"
os.environ["POSTGRES_PASSWORD"] = "test_password"

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings

from app.main import app
from config import get_settings


# =============================================================================
# Настройки для тестового окружения
# =============================================================================

class TestSettings(BaseSettings):
    """Настройки для тестового окружения (не наследуют от Settings)."""

    app_env: str = "test"
    postgres_host: str = "localhost"
    postgres_port: int = 5433  # Тестовая БД на порту 5433
    postgres_db: str = "test_vmeste"
    postgres_user: str = "test_user"
    postgres_password: str = "test_password"

    model_config = {
        "env_file": None,  # Не читать .env файл в тестах
        "frozen": True,
        "extra": "ignore",
    }

    @property
    def postgres_dsn(self) -> str:
        """Формирует DSN для подключения к тестовой PostgreSQL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@pytest.fixture(scope="session")
def test_settings() -> TestSettings:
    """Возвращает настройки для тестового окружения."""
    return TestSettings()


# =============================================================================
# Фикстуры для работы с тестовой БД
# =============================================================================

@pytest.fixture(scope="session")
def test_db_dsn(test_settings: TestSettings) -> str:
    """Возвращает DSN для подключения к тестовой БД."""
    return test_settings.postgres_dsn


@pytest.fixture(scope="function")
def db_connection(test_db_dsn: str) -> Generator[psycopg.Connection, None, None]:
    """
    Возвращает подключение к тестовой БД.

    Автоматически закрывает соединение после теста.
    """
    conn = psycopg.connect(test_db_dsn)
    yield conn
    conn.close()


@pytest.fixture
def clean_tables(db_connection: psycopg.Connection) -> None:
    """
    Очищает все таблицы перед каждым тестом.

    Использует TRUNCATE CASCADE для удаления данных из всех связанных таблиц.
    ВАЖНО: Больше не autouse=True! Используется только в integration/api тестах.
    """
    with db_connection.cursor() as cur:
        # Отключаем триггеры и очищаем таблицы
        cur.execute("""
            TRUNCATE TABLE
                users,
                sessions,
                chat_history,
                user_memory,
                sources,
                documents,
                content_chunks,
                chunk_embeddings_meta,
                psychologist_content,
                style_examples
            RESTART IDENTITY CASCADE
        """)
    db_connection.commit()


# =============================================================================
# Фикстуры для API тестов
# =============================================================================

@pytest.fixture
def client(test_settings: TestSettings) -> Generator[TestClient, None, None]:
    """
    Возвращает TestClient для API тестов.

    Переопределяет настройки приложения чтобы использовать тестовую БД.
    """
    # Переопределяем зависимость get_settings
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app) as test_client:
        yield test_client

    # Очищаем overrides после теста
    app.dependency_overrides.clear()


@pytest.fixture
def sample_user(client: TestClient) -> dict[str, Any]:
    """
    Создаёт тестового пользователя через API.

    Возвращает словарь с данными пользователя (включая user_id).
    Полезно для тестов которым нужен существующий пользователь.
    """
    response = client.post(
        "/users",
        json={
            "external_id": f"test-user-{uuid4()}",
            "email": f"test-{uuid4()}@example.com",
            "profile_json": {"test": True}
        }
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def sample_session(client: TestClient, sample_user: dict[str, Any]) -> dict[str, Any]:
    """
    Создаёт тестовую сессию для пользователя.

    Требует фикстуру sample_user.
    Возвращает данные сессии (включая session_id).
    """
    response = client.post(
        "/sessions",
        json={
            "user_id": sample_user["user_id"],
            "mode": "intake",
            "status": "active"
        }
    )
    assert response.status_code == 201
    return response.json()


# =============================================================================
# Моки для unit-тестов
# =============================================================================

@pytest.fixture
def mock_fetch_one(mocker):
    """Мокает функцию fetch_one из app.db.connection."""
    return mocker.patch("app.db.connection.fetch_one")


@pytest.fixture
def mock_fetch_all(mocker):
    """Мокает функцию fetch_all из app.db.connection."""
    return mocker.patch("app.db.connection.fetch_all")


@pytest.fixture
def mock_execute(mocker):
    """Мокает функцию execute из app.db.connection."""
    return mocker.patch("app.db.connection.execute")
