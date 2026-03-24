"""Единая операторская сводка по max_user_id (M4+M7+usage). Только с INTERNAL_DEBUG_KEY."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from packages.ops.operator_snapshot import build_launch_operator_snapshot
from packages.shared.settings import Settings, get_settings

router = APIRouter(prefix="/internal/launch", tags=["internal-launch"])


def _require_debug_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_debug_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.internal_debug_key or (x_internal_debug_key or "") != settings.internal_debug_key:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/user")
async def launch_operator_user_snapshot(
    request: Request,
    max_user_id: int,
    _auth: Annotated[None, Depends(_require_debug_key)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    factory = request.app.state.session_factory
    async with factory() as session:
        snap = await build_launch_operator_snapshot(session, settings=settings, max_user_id=max_user_id)
    if snap.get("error") == "user_not_found":
        raise HTTPException(status_code=404, detail="user not found")
    snap["meta"] = {
        "endpoint": "/internal/launch/user",
        "note": "Без секретов Т-Банка; RebillId маскирован.",
    }
    return snap
