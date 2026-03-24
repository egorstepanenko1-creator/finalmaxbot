"""Определение эффективного плана пользователя."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from packages.billing import subscription_states as ss
from packages.db.models import Subscription, User


def _month_start_utc() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def resolve_plan_code(session: Any, user: User) -> str:
    r = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        )
        .order_by(Subscription.id.desc())
        .limit(1)
    )
    sub = r.scalars().first()
    now = datetime.now(UTC)
    if not sub or sub.plan_code not in ("consumer_plus_290", "business_marketer_490"):
        return "business_free" if user.current_mode == "business" else "consumer_free"

    st = getattr(sub, "subscription_state", None) or ss.ACTIVE
    if st == ss.PENDING_ACTIVATION:
        return "business_free" if user.current_mode == "business" else "consumer_free"
    if st == ss.EXPIRED:
        return "business_free" if user.current_mode == "business" else "consumer_free"

    if sub.expires_at is not None:
        exp = sub.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp < now:
            return "business_free" if user.current_mode == "business" else "consumer_free"

    if st in ss.PAID_ACCESS_STATES:
        return sub.plan_code

    return "business_free" if user.current_mode == "business" else "consumer_free"
