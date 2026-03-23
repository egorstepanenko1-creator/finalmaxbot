"""Проверки квот и entitlements (M4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from packages.db.models import UsageEvent, User
from packages.entitlements.plan_definitions import PlanEntitlements, plan_entitlements_for
from packages.entitlements.resolver import resolve_plan_code
from packages.shared.settings import Settings

# События, расходующие «слот картинки» у consumer-планов
_CONSUMER_IMAGE_SLOT_KINDS = ("consumer_image_intake", "text_greeting")
# Legacy M3
_LEGACY_CONSUMER_IMAGE = "image_intake"


def _rolling_since() -> datetime:
    return datetime.now(UTC) - timedelta(hours=24)


def _month_start_utc() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class EntitlementDecision:
    allowed: bool
    reason: str
    plan_code: str
    detail: dict[str, Any]


class EntitlementService:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def _count_usage(
        self,
        session: Any,
        user_id: int,
        kinds: tuple[str, ...],
        since: datetime,
    ) -> int:
        r = await session.execute(
            select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= since,
                UsageEvent.kind.in_(kinds),
            )
        )
        return int(r.scalar() or 0)

    async def _count_legacy_consumer_image_intake(
        self, session: Any, user_id: int, since: datetime
    ) -> int:
        """image_intake без mode=business (старые строки)."""
        r = await session.execute(select(UsageEvent).where(
            UsageEvent.user_id == user_id,
            UsageEvent.created_at >= since,
            UsageEvent.kind == _LEGACY_CONSUMER_IMAGE,
        ))
        rows = r.scalars().all()
        n = 0
        for ev in rows:
            m = ev.meta or {}
            if m.get("mode") != "business":
                n += ev.units
        return n

    async def consumer_image_slots_used(
        self, session: Any, user_id: int, plan: PlanEntitlements, since_24h: datetime, month_start: datetime
    ) -> int:
        base = await self._count_usage(session, user_id, _CONSUMER_IMAGE_SLOT_KINDS, since_24h)
        base += await self._count_legacy_consumer_image_intake(session, user_id, since_24h)
        if plan.use_monthly_image_quota:
            m = await self._count_usage(session, user_id, _CONSUMER_IMAGE_SLOT_KINDS, month_start)
            m += await self._count_legacy_consumer_image_intake(session, user_id, month_start)
            return m
        return base

    async def business_image_slots_used_month(
        self, session: Any, user_id: int, month_start: datetime
    ) -> int:
        r = await session.execute(
            select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= month_start,
                UsageEvent.kind == "business_image_intake",
            )
        )
        n = int(r.scalar() or 0)
        # legacy
        r2 = await session.execute(
            select(UsageEvent).where(
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= month_start,
                UsageEvent.kind == _LEGACY_CONSUMER_IMAGE,
            )
        )
        for ev in r2.scalars().all():
            m = ev.meta or {}
            if m.get("mode") == "business":
                n += ev.units
        return n

    async def text_chats_used_rolling(self, session: Any, user_id: int) -> int:
        return await self._count_usage(session, user_id, ("text_question",), _rolling_since())

    async def vk_posts_used_month(self, session: Any, user_id: int) -> int:
        return await self._count_usage(session, user_id, ("text_vk_post",), _month_start_utc())

    async def evaluate(self, session: Any, user: User) -> tuple[str, PlanEntitlements]:
        code = await resolve_plan_code(session, user)
        return code, plan_entitlements_for(code, self._s)

    async def can_start_consumer_image_flow(self, session: Any, user: User) -> EntitlementDecision:
        plan_code, plan = await self.evaluate(session, user)
        if plan_code.startswith("business"):
            return EntitlementDecision(
                False, "wrong_mode", plan_code, {"message": "В бизнес-режиме используйте картинку из бизнес-меню."}
            )
        used = await self.consumer_image_slots_used(
            session, user.id, plan, _rolling_since(), _month_start_utc()
        )
        limit = (
            plan.max_image_events_per_calendar_month
            if plan.use_monthly_image_quota
            else plan.max_image_events_rolling_24h
        )
        if limit is not None and used >= limit:
            return EntitlementDecision(
                False,
                "image_quota_exhausted",
                plan_code,
                {"used": used, "limit": limit, "window": "month" if plan.use_monthly_image_quota else "rolling_24h"},
            )
        return EntitlementDecision(True, "ok", plan_code, {"used": used, "limit": limit})

    async def can_start_consumer_greeting_flow(self, session: Any, user: User) -> EntitlementDecision:
        """Поздравление расходует тот же пул, что и картинки (free rolling)."""
        return await self.can_start_consumer_image_flow(session, user)

    async def _business_image_used_rolling(self, session: Any, user_id: int, since: datetime) -> int:
        n = await self._count_usage(session, user_id, ("business_image_intake",), since)
        r2 = await session.execute(
            select(UsageEvent).where(
                UsageEvent.user_id == user_id,
                UsageEvent.created_at >= since,
                UsageEvent.kind == _LEGACY_CONSUMER_IMAGE,
            )
        )
        for ev in r2.scalars().all():
            m = ev.meta or {}
            if m.get("mode") == "business":
                n += ev.units
        return n

    async def business_image_used_rolling_24h(self, session: Any, user_id: int) -> int:
        return await self._business_image_used_rolling(session, user_id, _rolling_since())

    async def can_start_business_image_flow(self, session: Any, user: User) -> EntitlementDecision:
        plan_code, plan = await self.evaluate(session, user)
        if not plan_code.startswith("business"):
            return EntitlementDecision(False, "wrong_mode", plan_code, {})
        if plan.use_monthly_image_quota:
            used = await self.business_image_slots_used_month(session, user.id, _month_start_utc())
            lim = plan.max_image_events_per_calendar_month
            if lim is not None and used >= lim:
                return EntitlementDecision(
                    False,
                    "business_image_quota_exhausted",
                    plan_code,
                    {"used": used, "limit": lim},
                )
            return EntitlementDecision(True, "ok", plan_code, {"used": used, "limit": lim})

        used24 = await self._business_image_used_rolling(session, user.id, _rolling_since())
        lim24 = plan.max_image_events_rolling_24h
        if lim24 is not None and used24 >= lim24:
            return EntitlementDecision(
                False,
                "business_free_image_quota",
                plan_code,
                {"used": used24, "limit": lim24},
            )
        return EntitlementDecision(True, "ok", plan_code, {"used": used24, "limit": lim24})

    async def can_start_business_vk_flow(self, session: Any, user: User) -> EntitlementDecision:
        plan_code, plan = await self.evaluate(session, user)
        if not plan.vk_flow_enabled:
            return EntitlementDecision(
                False,
                "vk_not_entitled",
                plan_code,
                {"message": "Посты для VK доступны на тарифе business_marketer_490."},
            )
        used = await self.vk_posts_used_month(session, user.id)
        lim = plan.max_vk_posts_per_calendar_month
        if lim is not None and used >= lim:
            return EntitlementDecision(
                False, "vk_quota_exhausted", plan_code, {"used": used, "limit": lim}
            )
        return EntitlementDecision(True, "ok", plan_code, {"used": used, "limit": lim})

    async def can_complete_text_question(self, session: Any, user: User) -> EntitlementDecision:
        _, plan = await self.evaluate(session, user)
        used = await self.text_chats_used_rolling(session, user.id)
        lim = plan.max_text_chats_rolling_24h
        if used >= lim:
            return EntitlementDecision(
                False, "text_quota_exhausted", plan.plan_code, {"used": used, "limit": lim}
            )
        return EntitlementDecision(True, "ok", plan.plan_code, {"used": used, "limit": lim})

    def watermark_for_next_image_job(self, plan: PlanEntitlements) -> bool:
        return plan.watermark_on_image
