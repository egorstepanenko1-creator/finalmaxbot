"""Фоновые проходы: истечение периода и попытка MIT-продления (in-process / cron)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from packages.billing import subscription_states as ss
from packages.billing.factory import get_billing_service
from packages.billing.tbank_service import TBankBillingService
from packages.db.models import Subscription
from packages.shared.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)


async def expire_subscriptions_past_due(
    *,
    session_factory: async_sessionmaker[Any],
    billing: Any,
) -> list[int]:
    """Помечает истёкшие подписки; возвращает внутренние user_id для уведомлений MAX."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        r = await session.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.plan_code.in_(("consumer_plus_290", "business_marketer_490")),
                Subscription.expires_at.isnot(None),
            )
        )
        candidates: set[int] = set()
        for sub in r.scalars():
            exp = sub.expires_at
            if exp is None:
                continue
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp < now:
                candidates.add(sub.user_id)
        notified: list[int] = []
        for uid in candidates:
            if await billing.mark_subscription_expired(session=session, user_id=uid):
                notified.append(uid)
        await session.commit()
    for uid in notified:
        logger.info("m7_event=subscription_marked_expired user_id=%s", uid)
    return notified


async def run_renewal_charges(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[Any],
) -> int:
    """Init+Charge для подписок в окне до истечения. Только TBankBillingService."""
    if not getattr(settings, "m7_recurring_enabled", True):
        return 0
    billing = get_billing_service(settings)
    if not isinstance(billing, TBankBillingService):
        logger.info("m7_event=renewal_skipped reason=not_tbank_adapter")
        return 0
    now = datetime.now(UTC)
    advance = timedelta(hours=float(settings.m7_renewal_advance_hours))
    async with session_factory() as session:
        r = await session.execute(
            select(Subscription.id).where(
                Subscription.status == "active",
                Subscription.tbank_rebill_id.isnot(None),
                Subscription.auto_renew_enabled.is_(True),
                Subscription.subscription_state.notin((ss.CANCELLED, ss.EXPIRED)),
                Subscription.plan_code.in_(("consumer_plus_290", "business_marketer_490")),
                Subscription.expires_at.isnot(None),
            )
        )
        ids = [row[0] for row in r.all()]
    attempted = 0
    for sid in ids:
        async with session_factory() as session:
            r2 = await session.execute(select(Subscription).where(Subscription.id == sid))
            sub = r2.scalar_one_or_none()
            if sub is None:
                continue
            exp = sub.expires_at
            if exp is None:
                continue
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp < now:
                continue
            if exp > now + advance:
                continue
            meta = sub.meta or {}
            if meta.get("renewal_pending_payment_id"):
                continue
            res = await billing.run_mit_renewal_charge(session=session, sub=sub)
            await session.commit()
            if res.get("ok"):
                attempted += 1
    logger.info("m7_event=renewal_batch_done attempted=%s candidates=%s", attempted, len(ids))
    return attempted
