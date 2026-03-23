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
    if settings.tbank_terminal_key and not settings.tbank_password:
        logger.warning("m6_startup: TBANK_TERMINAL_KEY без TBANK_PASSWORD — эквайринг не включится")
    if settings.tbank_password and not settings.tbank_terminal_key:
        logger.warning("m6_startup: TBANK_PASSWORD без TBANK_TERMINAL_KEY")
    if settings.tbank_terminal_key and settings.tbank_password and not settings.tbank_notification_url:
        logger.warning(
            "m6_startup: TBANK_NOTIFICATION_URL пуст — задайте публичный HTTPS URL на POST /webhooks/tbank/notification"
        )
