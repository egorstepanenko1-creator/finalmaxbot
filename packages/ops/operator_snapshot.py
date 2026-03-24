"""Единая сводка пользователя для оператора (без секретов платежей)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from packages.db.models import BillingEvent, Referral, StarLedgerEntry, Subscription, UsageEvent, User
from packages.entitlements.plan_definitions import plan_entitlements_for
from packages.entitlements.resolver import resolve_plan_code
from packages.entitlements.service import EntitlementService
from packages.shared.settings import Settings


def _mask_rebill(rid: str | None) -> str:
    if not rid:
        return ""
    if len(rid) <= 4:
        return "****"
    return "****" + rid[-4:]


async def build_launch_operator_snapshot(
    session: Any,
    *,
    settings: Settings,
    max_user_id: int,
) -> dict[str, Any]:
    r = await session.execute(select(User).where(User.max_user_id == max_user_id))
    user = r.scalar_one_or_none()
    if user is None:
        return {"error": "user_not_found", "max_user_id": max_user_id}

    ent = EntitlementService(settings)
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
        select(func.coalesce(func.sum(StarLedgerEntry.delta), 0)).where(StarLedgerEntry.user_id == user.id)
    )
    stars_sum = int(stars.scalar() or 0)

    ref_rows = (
        (await session.execute(select(Referral).where(
            (Referral.inviter_user_id == user.id) | (Referral.invitee_user_id == user.id)
        ))).scalars().all()
    )

    subs = (
        (await session.execute(select(Subscription).where(Subscription.user_id == user.id)))
        .scalars()
        .all()
    )

    latest_sub = None
    for s in sorted(subs, key=lambda x: x.id, reverse=True):
        if s.status == "active":
            latest_sub = s
            break
    if latest_sub is None and subs:
        latest_sub = max(subs, key=lambda x: x.id)

    usage_rows = (
        (
            await session.execute(
                select(UsageEvent)
                .where(UsageEvent.user_id == user.id)
                .order_by(UsageEvent.id.desc())
                .limit(15)
            )
        )
        .scalars()
        .all()
    )

    bill_rows = (
        (
            await session.execute(
                select(BillingEvent)
                .where(BillingEvent.user_id == user.id)
                .order_by(BillingEvent.id.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )

    return {
        "max_user_id": max_user_id,
        "internal_user_id": user.id,
        "onboarding_state": user.onboarding_state,
        "current_mode": user.current_mode,
        "effective_plan_code": plan_code,
        "entitlements": {
            "watermark_on_image": plan.watermark_on_image,
            "premium_style_enabled": plan.premium_style_enabled,
            "vk_flow_enabled": plan.vk_flow_enabled,
            "use_monthly_image_quota": plan.use_monthly_image_quota,
        },
        "quotas": {
            "consumer_image_slots_used_24h_or_month_rule": img_used,
            "business_image_used_month": bus_img,
            "business_image_used_rolling_24h": bus_roll,
            "text_chats_used_rolling_24h": txt_used,
            "vk_posts_used_month": vk_used,
        },
        "stars_balance_sum_delta": stars_sum,
        "referral": {
            "my_code": user.referral_code,
            "referred_by_user_id": user.referred_by_user_id,
            "links": [
                {
                    "id": x.id,
                    "inviter_user_id": x.inviter_user_id,
                    "invitee_user_id": x.invitee_user_id,
                    "status": x.status,
                    "reward_granted_at": x.reward_granted_at.isoformat() if x.reward_granted_at else None,
                }
                for x in ref_rows
            ],
        },
        "subscription_latest": (
            None
            if latest_sub is None
            else {
                "id": latest_sub.id,
                "plan_code": latest_sub.plan_code,
                "row_status": latest_sub.status,
                "subscription_state": latest_sub.subscription_state,
                "expires_at": latest_sub.expires_at.isoformat() if latest_sub.expires_at else None,
                "auto_renew_enabled": latest_sub.auto_renew_enabled,
                "cancelled_at": latest_sub.cancelled_at.isoformat() if latest_sub.cancelled_at else None,
                "tbank_rebill_masked": _mask_rebill(latest_sub.tbank_rebill_id),
                "has_rebill_id": bool(latest_sub.tbank_rebill_id),
            }
        ),
        "subscriptions_all_brief": [
            {
                "id": s.id,
                "plan_code": s.plan_code,
                "status": s.status,
                "subscription_state": s.subscription_state,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in sorted(subs, key=lambda x: x.id, reverse=True)[:8]
        ],
        "usage_recent": [
            {
                "kind": u.kind,
                "units": u.units,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in usage_rows
        ],
        "billing_events_recent": [
            {
                "outcome": b.outcome,
                "event_type": b.event_type,
                "order_id": b.order_id,
                "plan_code": b.plan_code,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bill_rows
        ],
    }
