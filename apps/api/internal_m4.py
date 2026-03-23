"""Внутренние эндпоинты для проверки M4 (без секретов в ответе)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from packages.billing.stub_service import StubBillingCheckoutService
from packages.db.models import Referral, StarLedgerEntry, Subscription, User
from packages.entitlements.plan_definitions import plan_entitlements_for
from packages.entitlements.resolver import resolve_plan_code
from packages.entitlements.service import EntitlementService
from packages.shared.settings import Settings, get_settings

router = APIRouter(prefix="/internal/m4", tags=["internal-m4"])


def _require_debug_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_debug_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.internal_debug_key or (x_internal_debug_key or "") != settings.internal_debug_key:
        raise HTTPException(status_code=404, detail="not found")


class ActivateBody(BaseModel):
    max_user_id: int
    plan_code: str


@router.get("/summary")
async def m4_summary(
    request: Request,
    max_user_id: int,
    _auth: Annotated[None, Depends(_require_debug_key)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    factory = request.app.state.session_factory
    ent = EntitlementService(settings)
    async with factory() as session:
        r = await session.execute(select(User).where(User.max_user_id == max_user_id))
        user = r.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        plan_code = await resolve_plan_code(session, user)
        plan = plan_entitlements_for(plan_code, settings)
        since24 = datetime.now(UTC) - timedelta(hours=24)
        ms = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        img_used = await ent.consumer_image_slots_used(session, user.id, plan, since24, ms)
        bus_img = await ent.business_image_slots_used_month(session, user.id, ms)
        bus_roll = await ent.business_image_used_rolling_24h(session, user.id)
        txt_used = await ent.text_chats_used_rolling(session, user.id)
        vk_used = await ent.vk_posts_used_month(session, user.id)

        stars = await session.execute(
            select(func.coalesce(func.sum(StarLedgerEntry.delta), 0)).where(
                StarLedgerEntry.user_id == user.id
            )
        )
        stars_sum = int(stars.scalar() or 0)

        ref_rows = (
            (
                await session.execute(
                    select(Referral).where(
                        (Referral.inviter_user_id == user.id)
                        | (Referral.invitee_user_id == user.id)
                    )
                )
            )
            .scalars()
            .all()
        )
        subs = (
            (await session.execute(select(Subscription).where(Subscription.user_id == user.id)))
            .scalars()
            .all()
        )

        return {
            "max_user_id": max_user_id,
            "internal_user_id": user.id,
            "current_mode": user.current_mode,
            "effective_plan_code": plan_code,
            "entitlements": {
                "watermark_on_image": plan.watermark_on_image,
                "premium_style_enabled": plan.premium_style_enabled,
                "vk_flow_enabled": plan.vk_flow_enabled,
                "use_monthly_image_quota": plan.use_monthly_image_quota,
            },
            "quotas": {
                "consumer_image_slots_used": img_used,
                "business_image_used_month": bus_img,
                "business_image_used_rolling_24h": bus_roll,
                "text_chats_used_rolling_24h": txt_used,
                "vk_posts_used_month": vk_used,
            },
            "stars_balance_sum_delta": stars_sum,
            "referral_code": user.referral_code,
            "referred_by_user_id": user.referred_by_user_id,
            "referrals": [
                {
                    "id": x.id,
                    "inviter_user_id": x.inviter_user_id,
                    "invitee_user_id": x.invitee_user_id,
                    "status": x.status,
                    "reward_granted_at": x.reward_granted_at.isoformat()
                    if x.reward_granted_at
                    else None,
                }
                for x in ref_rows
            ],
            "subscriptions": [
                {"id": s.id, "plan_code": s.plan_code, "status": s.status} for s in subs
            ],
        }


@router.post("/subscription/activate-stub")
async def activate_stub_subscription(
    request: Request,
    body: ActivateBody,
    _auth: Annotated[None, Depends(_require_debug_key)],
) -> dict[str, Any]:
    factory = request.app.state.session_factory
    billing = StubBillingCheckoutService()
    async with factory() as session:
        r = await session.execute(select(User).where(User.max_user_id == body.max_user_id))
        user = r.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        act = await billing.activate_subscription(
            session=session,
            user_id=user.id,
            plan_code=body.plan_code,
            external_payment_id="debug_stub",
        )
        await session.commit()
        return {
            "ok": True,
            "user_id": act.user_id,
            "plan_code": act.plan_code,
            "status": act.status,
        }
