from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MAX Bot API (https://dev.max.ru/docs-api)
    max_bot_token: str | None = None
    max_api_base: str = "https://platform-api.max.ru"
    max_webhook_secret: str | None = None

    # Postgres (Supabase) или локально sqlite+aiosqlite
    database_url: str = "sqlite+aiosqlite:///./finalmaxbot.db"

    # Для проверки REST (опционально)
    supabase_url: str | None = None
    supabase_anon_key: str | None = None

    # Если false — не дергаем platform-api (только логи); удобно без токена
    max_outbound_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


def normalize_async_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    return url
