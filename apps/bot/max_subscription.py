"""Регистрация webhook в MAX API (как max-bot-mvp registerWebhookIfNeeded)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


async def register_max_webhook_if_configured(settings: Settings) -> None:
    """
    POST /subscriptions: url = PUBLIC_BASE_URL + MAX_WEBHOOK_PATH.
    Нужны MAX_BOT_TOKEN, MAX_AUTO_REGISTER_WEBHOOK=true, PUBLIC_BASE_URL.
    """
    if not settings.max_auto_register_webhook:
        return
    token = (settings.max_bot_token or "").strip()
    base_public = (settings.public_base_url or "").strip().rstrip("/")
    if not token:
        logger.warning("max_subscription: MAX_AUTO_REGISTER_WEBHOOK без MAX_BOT_TOKEN — пропуск")
        return
    if not base_public:
        logger.warning("max_subscription: MAX_AUTO_REGISTER_WEBHOOK без PUBLIC_BASE_URL — пропуск")
        return
    path = settings.max_webhook_path.strip() or "/webhooks/max"
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base_public}{path}"
    api = settings.max_api_base.rstrip("/")
    body: dict[str, Any] = {
        "url": url,
        "update_types": ["message_created", "bot_started", "message_callback"],
    }
    if settings.max_webhook_secret:
        body["secret"] = settings.max_webhook_secret
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{api}/subscriptions",
                headers={"Authorization": token, "Content-Type": "application/json"},
                json=body,
            )
        if r.status_code >= 400:
            logger.warning(
                "max_subscription: POST /subscriptions failed %s %s",
                r.status_code,
                r.text[:500],
            )
            return
        logger.info("max_subscription: webhook registered url=%s", url)
    except Exception:
        logger.exception("max_subscription: register failed")
