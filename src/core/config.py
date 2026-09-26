from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Northwind Support API"

    # Browser origins allowed to call the API: the chat widget and, later, the agent dashboard.
    cors_origins: list[str] = ["http://localhost:3000"]

    # SQLite now; switching to Postgres (Tiger Data) is a URL change, e.g. postgresql+asyncpg://...
    database_url: str = "sqlite+aiosqlite:///./northwind.db"

    gemini_api_key: SecretStr
    gemini_model: str = "gemini-3.5-flash-lite"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
