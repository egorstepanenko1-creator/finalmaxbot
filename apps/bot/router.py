import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from apps.bot.max_client import MaxBotClient
from apps.bot.max_dispatch import dispatch_max_update
from apps.bot.max_payload import extract_outbound_max_chat_id
from apps.bot.outbound_context import outbound_max_chat_id
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

    factory = request.app.state.session_factory

    ctx_tok = outbound_max_chat_id.set(extract_outbound_max_chat_id(body))
    try:
        result = await dispatch_max_update(
            body,
            session_factory=factory,
            client=client,
            settings=settings,
        )
        if result == "duplicate":
            return {"ok": "true", "duplicate": "1"}
        return {"ok": "true"}
    finally:
        outbound_max_chat_id.reset(ctx_tok)
