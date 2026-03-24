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
    # webhook | polling — при polling входящие через GET /updates (локальная отладка)
    max_mode: str = "webhook"
    # Публичный URL (ngrok) для авто-регистрации webhook: PUBLIC_BASE_URL + MAX_WEBHOOK_PATH
    public_base_url: str | None = None
    max_webhook_path: str = "/webhooks/max"
    max_auto_register_webhook: bool = False
    max_poll_limit: int = 50
    max_poll_timeout_sec: int = 30

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

    # --- M5: выдача контента, хранилище, водяной знак, Yandex Art (опционально) ---
    m5_local_storage_root: str = "./data/generated"
    m5_watermark_text: str = "Free"
    m5_watermark_opacity: float = 0.35
    m5_max_upload_ready_delay_sec: float = 0.75
    m5_max_send_attachment_retries: int = 5
    yandex_image_generation_enabled: bool = False
    yandex_image_model_uri: str | None = None
    yandex_image_async_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
    yandex_image_operations_url_template: str = "https://llm.api.cloud.yandex.net/operations/{operation_id}"
    yandex_image_poll_interval_sec: float = 2.0
    yandex_image_poll_timeout_sec: float = 120.0

    # --- M6: Т-Банк (эквайринг v2), webhook, подписки ---
    tbank_terminal_key: str | None = None
    tbank_password: str | None = None
    tbank_api_base: str = "https://securepay.tinkoff.ru/v2"
    tbank_notification_url: str | None = None
    tbank_success_url: str | None = None
    tbank_payment_description_prefix: str = "finalmaxbot:"
    tbank_skip_signature_verify: bool = False
    m6_subscription_period_days: int = 30
    m6_require_max_token_if_outbound: bool = True

    # M7: рекуррент (Т-Банк Init Recurrent=Y + MIT Charge)
    m7_recurring_enabled: bool = True
    m7_renewal_advance_hours: float = 36.0


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
