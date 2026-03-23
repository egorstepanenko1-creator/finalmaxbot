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

    # YandexGPT / Foundation Models (опционально; иначе stub)
    yandex_cloud_api_key: str | None = None
    yandex_folder_id: str | None = None
    # Например: gpt://<folder_id>/yandexgpt/latest
    yandex_model_uri: str | None = None
    yandex_completion_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    # --- M4 monetization / quotas (config-driven) ---
    m4_consumer_free_images_per_rolling_24h: int = 3
    m4_consumer_free_text_chats_per_rolling_24h: int = 15
    m4_consumer_plus_max_images_per_month: int = 120
    m4_consumer_plus_text_chats_per_rolling_24h: int = 100
    m4_business_free_images_per_rolling_24h: int = 3
    m4_business_free_text_chats_per_rolling_24h: int = 20
    m4_business_marketer_max_images_per_month: int = 120
    m4_business_marketer_max_vk_posts_per_month: int = 30
    m4_business_marketer_text_chats_per_rolling_24h: int = 100

    # Схема: Alembic по умолчанию; create_all только если явно включено (локалка)
    run_alembic_on_startup: bool = True
    allow_runtime_create_all: bool = False

    # Внутренние debug-эндпоинты: если пусто — отключены
    internal_debug_key: str | None = None


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
