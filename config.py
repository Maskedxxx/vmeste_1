# config.py
# --- agent_meta ---
# role: application-config
# contract: предоставляет настройки приложения и соединение с БД
# owner: backend-core
# --- /agent_meta ---

"""Глобальная конфигурация приложения."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Параметры приложения и инфраструктуры."""

    app_env: Literal["development", "production", "test"] = Field(
        "development",
        alias="APP_ENV",
        description="Текущее окружение приложения.",
    )

    postgres_host: str = Field("vmeste-postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("vmeste", alias="POSTGRES_DB")
    postgres_user: str = Field("vmeste", alias="POSTGRES_USER")
    postgres_password: str = Field("vmeste_password", alias="POSTGRES_PASSWORD")
    openai_model: str = Field(
        "gpt-4.1-mini",
        alias="OPENAI_MODEL",
        description="Модель OpenAI, используемая для генерации профиля.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        """Формирует DSN для подключения к PostgreSQL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает singleton с настройками приложения."""
    return Settings()


if __name__ == "__main__":
    settings = get_settings()
    print("Текущее окружение:", settings.app_env)
    print("PostgreSQL DSN:", settings.postgres_dsn)
