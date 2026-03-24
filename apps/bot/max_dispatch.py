"""Общая обработка MAX update: webhook и long polling."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from apps.bot.handlers import handle_max_update
from apps.bot.max_client import MaxBotClient
from apps.bot.webhook_idempotency import compute_idempotency_key
from packages.db.models import WebhookProcessed, WebhookRawEvent
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


async def dispatch_max_update(
    body: dict[str, Any],
    *,
    session_factory: Any,
    client: MaxBotClient,
    settings: Settings,
) -> Literal["ok", "duplicate"]:
    """
    Логирует сырое событие, идемпотентность, state machine, after_commit tasks.
    Вызывать с уже выставленным outbound_max_chat_id или обернуть снаружи.
    """
    key = compute_idempotency_key(body)
    body_str = json.dumps(body, ensure_ascii=False)

    async with session_factory() as log_session:
        log_session.add(WebhookRawEvent(idempotency_key=key, body_json=body_str))
        await log_session.commit()

    after_commit: list[Any] = []
    async with session_factory() as session:
        existing = await session.get(WebhookProcessed, key)
        if existing is not None:
            logger.info("max update duplicate skipped key=%s", key)
            return "duplicate"

        await handle_max_update(
            body,
            session=session,
            session_factory=session_factory,
            client=client,
            settings=settings,
            after_commit=after_commit,
        )
        session.add(WebhookProcessed(idempotency_key=key))
        await session.commit()

    for fn in after_commit:
        asyncio.create_task(fn())

    return "ok"
