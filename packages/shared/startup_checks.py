"""Предупреждения при старте (staging / launch)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


def warn_launch_readiness(settings: Settings) -> None:
    if settings.m6_require_max_token_if_outbound and settings.max_outbound_enabled and not settings.max_bot_token:
        logger.warning(
            "m6_startup: MAX_OUTBOUND_ENABLED=true, но MAX_BOT_TOKEN пуст — исходящие сообщения не дойдут"
        )
    if not settings.max_webhook_secret:
        logger.warning(
            "m6_startup: MAX_WEBHOOK_SECRET пуст — рекомендуется задать для production webhook"
        )
    mode = settings.max_mode.strip().lower()
    if mode == "polling" and not (settings.max_bot_token or "").strip():
        logger.warning("m6_startup: MAX_MODE=polling без MAX_BOT_TOKEN — входящие не придут")
    if settings.max_auto_register_webhook and not (settings.public_base_url or "").strip():
        logger.warning(
            "m6_startup: MAX_AUTO_REGISTER_WEBHOOK=true без PUBLIC_BASE_URL — регистрация webhook пропущена"
        )
    if settings.max_auto_register_webhook and mode == "polling":
        logger.warning(
            "m6_startup: MAX_AUTO_REGISTER_WEBHOOK при MAX_MODE=polling — обычно нужен только один способ доставки"
        )
    if settings.tbank_terminal_key and not settings.tbank_password:
        logger.warning("m6_startup: TBANK_TERMINAL_KEY без TBANK_PASSWORD — эквайринг не включится")
    if settings.tbank_password and not settings.tbank_terminal_key:
        logger.warning("m6_startup: TBANK_PASSWORD без TBANK_TERMINAL_KEY")
    if settings.tbank_terminal_key and settings.tbank_password and not settings.tbank_notification_url:
        logger.warning(
            "m6_startup: TBANK_NOTIFICATION_URL пуст — задайте публичный HTTPS URL на POST /webhooks/tbank/notification"
        )
