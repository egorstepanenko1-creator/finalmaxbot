"""M7: безопасный debug-просмотр подписки и биллинга (только с INTERNAL_DEBUG_KEY)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select

from packages.db.models import BillingEvent, Subscription, User
from packages.entitlements.resolver import resolve_plan_code
from packages.shared.settings import Settings, get_settings

router = APIRouter(prefix="/internal/m7", tags=["internal-m7"])


def _require_debug_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_debug_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.internal_debug_key or (x_internal_debug_key or "") != settings.internal_debug_key:
        raise HTTPException(status_code=404, detail="not found")


def _mask_rebill(rid: str | None) -> str:
    if not rid:
        return ""
    if len(rid) <= 4:
        return "****"
    return "****" + rid[-4:]


@router.get("/subscription")
async def m7_subscription_debug(
    request: Request,
    max_user_id: int,
    _auth: Annotated[None, Depends(_require_debug_key)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    factory = request.app.state.session_factory
    async with factory() as session:
        r = await session.execute(select(User).where(User.max_user_id == max_user_id))
        user = r.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        internal_uid = user.id
        effective_plan = await resolve_plan_code(session, user)
        subs_r = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == internal_uid)
            .order_by(Subscription.id.desc())
            .limit(5)
        )
        subs = subs_r.scalars().all()
        ev_r = await session.execute(
            select(BillingEvent)
            .where(BillingEvent.user_id == internal_uid)
            .order_by(BillingEvent.id.desc())
            .limit(10)
        )
        events = ev_r.scalars().all()
    sub_payload = []
    for s in subs:
        exp = s.expires_at.isoformat() if s.expires_at else None
        sub_payload.append(
            {
                "id": s.id,
                "plan_code": s.plan_code,
                "status": s.status,
                "subscription_state": s.subscription_state,
                "expires_at": exp,
                "auto_renew_enabled": s.auto_renew_enabled,
                "cancelled_at": s.cancelled_at.isoformat() if s.cancelled_at else None,
                "tbank_rebill_masked": _mask_rebill(s.tbank_rebill_id),
                "has_rebill_id": bool(s.tbank_rebill_id),
                "tbank_customer_key_set": bool(s.tbank_customer_key),
                "tbank_parent_payment_id_set": bool(s.tbank_parent_payment_id),
            }
        )
    ev_payload = [
        {
            "id": e.id,
            "outcome": e.outcome,
            "event_type": e.event_type,
            "order_id": e.order_id,
            "plan_code": e.plan_code,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
    return {
        "max_user_id": max_user_id,
        "internal_user_id": internal_uid,
        "effective_plan_code": effective_plan,
        "m7_recurring_enabled": getattr(settings, "m7_recurring_enabled", True),
        "subscriptions_recent": sub_payload,
        "billing_events_recent": ev_payload,
    }
