"""Проверка доступности БД. Только с INTERNAL_DEBUG_KEY."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from packages.db.session import ping_database
from packages.shared.settings import Settings, get_settings

router = APIRouter(prefix="/internal/debug", tags=["internal-debug"])

_DB_PING_TIMEOUT_SEC = 10.0


def _require_debug_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_debug_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.internal_debug_key or (x_internal_debug_key or "") != settings.internal_debug_key:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/db-ping")
async def debug_db_ping(
    request: Request,
    _auth: Annotated[None, Depends(_require_debug_key)],
) -> dict[str, object]:
    engine = request.app.state.engine
    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(_DB_PING_TIMEOUT_SEC):
            await ping_database(engine)
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={"ok": False, "error": f"timeout_after_{_DB_PING_TIMEOUT_SEC}s"},
        ) from None
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"ok": False, "error": type(e).__name__, "message": str(e)[:500]},
        ) from None
    ms = (time.perf_counter() - t0) * 1000
    return {"ok": True, "latency_ms": round(ms, 2)}
