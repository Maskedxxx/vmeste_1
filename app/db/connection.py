# app/db/connection.py
# --- agent_meta ---
# role: db-connection
# contract: управляет пулом соединений и выполнением SQL-запросов
# owner: backend-core
# --- /agent_meta ---

"""Утилиты для работы с соединениями PostgreSQL."""

from contextlib import contextmanager
from typing import Any, Generator, Mapping, Sequence
import logging

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from config import get_settings


logger = logging.getLogger("vmeste.db.connection")

_settings = get_settings()

_pool = ConnectionPool(
    conninfo=_settings.postgres_dsn,
    min_size=1,
    max_size=5,
    kwargs={"autocommit": True},
)


@contextmanager
def get_connection() -> Generator[psycopg.Connection[Any], None, None]:
    """Возвращает подключение из пула."""
    with _pool.connection() as connection:
        yield connection


def fetch_all(query: str, params: Mapping[str, Any] | None = None) -> list[DictRow]:
    """Выполняет SELECT и возвращает все строки."""
    logger.debug("SQL fetch_all: %s | %s", query, params)
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params or {})
            rows = cursor.fetchall()
    return rows


def fetch_one(query: str, params: Mapping[str, Any] | None = None) -> DictRow | None:
    """Возвращает одну строку или None."""
    logger.debug("SQL fetch_one: %s | %s", query, params)
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params or {})
            row = cursor.fetchone()
    return row


def execute(query: str, params: Mapping[str, Any] | None = None) -> None:
    """Выполняет INSERT/UPDATE/DELETE без возврата данных."""
    logger.debug("SQL execute: %s | %s", query, params)
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params or {})


def fetch_many(
    query: str,
    params_seq: Sequence[Mapping[str, Any]],
) -> list[list[DictRow]]:
    """Выполняет запрос для набора параметров (batch)."""
    results: list[list[DictRow]] = []
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            for params in params_seq:
                logger.debug("SQL fetch_many: %s | %s", query, params)
                cursor.execute(query, params)
                results.append(cursor.fetchall())
    return results


if __name__ == "__main__":
    test_query = "SELECT 1 AS ready"
    print("Проверка пула:", fetch_one(test_query))
