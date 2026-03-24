"""Long polling GET /updates (локальная отладка без кабинета), как max-bot-mvp."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import FastAPI

from apps.bot.max_client import MaxBotClient
from apps.bot.max_dispatch import dispatch_max_update
from apps.bot.max_payload import extract_outbound_max_chat_id
from apps.bot.outbound_context import outbound_max_chat_id
from packages.shared.settings import get_settings

logger = logging.getLogger(__name__)


def _updates_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("updates",):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    data = payload.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        u = data.get("updates")
        if isinstance(u, list):
            return [x for x in u if isinstance(x, dict)]
    result = payload.get("result")
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        u = result.get("updates")
        if isinstance(u, list):
            return [x for x in u if isinstance(x, dict)]
    return []


def _extract_marker(payload: Any, previous: str | None) -> str | None:
    if not isinstance(payload, dict):
        return previous
    m = payload.get("marker")
    if m is not None and str(m).strip() != "":
        return str(m)
    data = payload.get("data")
    if isinstance(data, dict):
        m2 = data.get("marker")
        if m2 is not None and str(m2).strip() != "":
            return str(m2)
    result = payload.get("result")
    if isinstance(result, dict):
        m3 = result.get("marker")
        if m3 is not None and str(m3).strip() != "":
            return str(m3)
    return previous


async def max_long_polling_loop(app: FastAPI) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    token = (settings.max_bot_token or "").strip()
    if not token:
        logger.error("max_polling: нет MAX_BOT_TOKEN — цикл не запущен")
        return
    api = settings.max_api_base.rstrip("/")
    client = MaxBotClient(settings)
    factory = app.state.session_factory
    marker: str | None = getattr(app.state, "max_poll_marker", None)
    limit = max(1, min(100, settings.max_poll_limit))
    timeout = max(1, min(120, settings.max_poll_timeout_sec))
    logger.info(
        "max_polling: старт long poll limit=%s timeout=%s marker=%s",
        limit,
        timeout,
        marker,
    )
    while True:
        try:
            params: dict[str, str | int] = {
                "limit": limit,
                "timeout": timeout,
                "types": "message_created,bot_started,message_callback",
            }
            if marker is not None:
                params["marker"] = marker
            async with httpx.AsyncClient(timeout=float(timeout) + 15.0) as hc:
                r = await hc.get(
                    f"{api}/updates",
                    params=params,
                    headers={"Authorization": token},
                )
            if r.status_code >= 400:
                logger.warning("max_polling: GET /updates %s %s", r.status_code, r.text[:400])
                await asyncio.sleep(3.0)
                continue
            try:
                payload = r.json()
            except Exception:
                logger.warning("max_polling: ответ не JSON")
                await asyncio.sleep(3.0)
                continue
            marker = _extract_marker(payload, marker)
            app.state.max_poll_marker = marker
            updates = _updates_list(payload)
            if updates:
                logger.info("max_polling: получено updates=%s", len(updates))
            for body in updates:
                ctx_tok = outbound_max_chat_id.set(extract_outbound_max_chat_id(body))
                try:
                    await dispatch_max_update(
                        body,
                        session_factory=factory,
                        client=client,
                        settings=settings,
                    )
                finally:
                    outbound_max_chat_id.reset(ctx_tok)
        except asyncio.CancelledError:
            logger.info("max_polling: остановка")
            raise
        except Exception:
            logger.exception("max_polling: ошибка цикла")
            await asyncio.sleep(3.0)
