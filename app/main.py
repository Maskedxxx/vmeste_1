"""Точка входа FastAPI-приложения для проекта «Вместе» (v0)."""

from logging import INFO, basicConfig, getLogger
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


basicConfig(level=INFO)
logger = getLogger("vmeste.api")


class HealthResponse(BaseModel):
    """Ответ сервиса на проверку работоспособности."""

    status: Literal["ok"]


app = FastAPI(title="Vmeste API", version="0.1.0")


@app.get("/health", response_model=HealthResponse, tags=["service"])
def health_check() -> HealthResponse:
    """Возвращает статус сервиса."""
    logger.debug("Получен запрос /health")
    return HealthResponse(status="ok")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
