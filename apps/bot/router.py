import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from apps.bot.handlers import handle_max_update
from apps.bot.max_client import MaxBotClient
from apps.bot.webhook_idempotency import compute_idempotency_key
from packages.db.models import WebhookProcessed, WebhookRawEvent
from packages.shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["max"])


def get_max_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MaxBotClient:
    return MaxBotClient(settings)


@router.post("/webhooks/max")
async def max_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[MaxBotClient, Depends(get_max_client)],
    x_max_bot_api_secret: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if settings.max_webhook_secret:
        if (x_max_bot_api_secret or "") != settings.max_webhook_secret:
            raise HTTPException(status_code=401, detail="invalid webhook secret")

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="expected json object")

    key = compute_idempotency_key(body)
    body_str = json.dumps(body, ensure_ascii=False)
    factory = request.app.state.session_factory

    async with factory() as log_session:
        log_session.add(WebhookRawEvent(idempotency_key=key, body_json=body_str))
        await log_session.commit()

    after_commit: list[Any] = []
    async with factory() as session:
        existing = await session.get(WebhookProcessed, key)
        if existing is not None:
            logger.info("webhook duplicate skipped key=%s", key)
            return {"ok": "true", "duplicate": "1"}

        await handle_max_update(
            body,
            session=session,
            session_factory=factory,
            client=client,
            settings=settings,
            after_commit=after_commit,
        )
        session.add(WebhookProcessed(idempotency_key=key))
        await session.commit()

    for fn in after_commit:
        asyncio.create_task(fn())

    return {"ok": "true"}
