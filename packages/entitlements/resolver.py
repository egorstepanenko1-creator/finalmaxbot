"""Определение эффективного плана пользователя."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

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
    if sub and sub.plan_code in (
        "consumer_plus_290",
        "business_marketer_490",
    ):
        return sub.plan_code
    if user.current_mode == "business":
        return "business_free"
    return "consumer_free"
