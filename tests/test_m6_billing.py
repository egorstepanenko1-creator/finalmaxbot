"""M6: Т-Банк webhook, идемпотентность, paywall → план, entitlements по подписке."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

import packages.shared.callbacks as cb
from packages.billing.stub_service import StubBillingCheckoutService
from packages.billing.webhook_logic import process_tbank_notification_json
from packages.db.models import BillingEvent, Subscription, User
from packages.entitlements.resolver import resolve_plan_code


def _tbank_body(*, user_id: int, payment_id: str, plan: str) -> dict[str, object]:
    return {
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": payment_id,
        "OrderId": f"fm_{user_id}_testorder",
        "DATA": json.dumps({"user_id": str(user_id), "plan_code": plan}),
        "Token": "dummy",
    }


def _plan_from_paywall_segments(segments: list[str], *, user_mode: str) -> str:
    """Зеркалит ветку paywall в state_machine_service (без I/O)."""
    if cb.is_v1_paywall_action(segments, "subscribe_consumer_plus"):
        return "consumer_plus_290"
    if cb.is_v1_paywall_action(segments, "subscribe_business"):
        return "business_marketer_490"
    return "consumer_plus_290" if user_mode == "consumer" else "business_marketer_490"


async def test_tbank_webhook_activates_plan(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=880001, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id

    body = _tbank_body(user_id=uid, payment_id="pay-m6-act-1", plan="consumer_plus_290")
    async with session_factory() as s:
        res = await process_tbank_notification_json(
            session=s,
            body=body,
            billing=billing,
            verify_token=lambda _b: True,
        )
    assert res.ok is True
    assert res.reason == "activated"
    assert res.user_id == uid

    async with session_factory() as s:
        r = await s.execute(
            select(Subscription).where(Subscription.user_id == uid, Subscription.status == "active")
        )
        sub = r.scalars().first()
        assert sub is not None
        assert sub.plan_code == "consumer_plus_290"
        assert sub.expires_at is not None


async def test_duplicate_tbank_callback_idempotent(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=880002, current_mode="business", onboarding_state="mode_set")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id

    body = _tbank_body(user_id=uid, payment_id="pay-m6-dup-1", plan="business_marketer_490")
    async with session_factory() as s:
        res1 = await process_tbank_notification_json(
            session=s,
            body=body,
            billing=billing,
            verify_token=lambda _b: True,
        )
    async with session_factory() as s:
        res2 = await process_tbank_notification_json(
            session=s,
            body=body,
            billing=billing,
            verify_token=lambda _b: True,
        )
    assert res1.reason == "activated"
    assert res2.reason == "duplicate"
    assert res1.ok and res2.ok

    async with session_factory() as s:
        n_act = await s.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.user_id == uid, Subscription.status == "active")
        )
        assert n_act == 1
        n_ev = await s.scalar(
            select(func.count()).select_from(BillingEvent).where(BillingEvent.idempotency_key == "pay-m6-dup-1")
        )
        assert n_ev == 1


def test_paywall_payload_maps_to_checkout_plan() -> None:
    raw_c = cb.PAYWALL_SUBSCRIBE_CONSUMER_PLUS
    ver, segs = cb.parse_payload(raw_c)
    assert ver == cb.VER
    assert cb.is_paywall_subscribe_variant(segs)
    assert _plan_from_paywall_segments(segs, user_mode="consumer") == "consumer_plus_290"

    raw_b = cb.PAYWALL_SUBSCRIBE_BUSINESS_PLAN
    ver_b, segs_b = cb.parse_payload(raw_b)
    assert ver_b == cb.VER
    assert _plan_from_paywall_segments(segs_b, user_mode="business") == "business_marketer_490"


async def test_active_subscription_unlocks_plan(session_factory) -> None:
    async with session_factory() as s:
        u = User(max_user_id=880003, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        fut = datetime.now(UTC) + timedelta(days=10)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                expires_at=fut,
            )
        )
        await s.commit()

    async with session_factory() as s:
        u2 = (await s.execute(select(User).where(User.id == u.id))).scalar_one()
        assert await resolve_plan_code(s, u2) == "consumer_plus_290"


async def test_expired_subscription_falls_back_to_free(session_factory) -> None:
    async with session_factory() as s:
        u = User(max_user_id=880004, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        past = datetime.now(UTC) - timedelta(days=1)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                expires_at=past,
            )
        )
        await s.commit()

    async with session_factory() as s:
        u2 = (await s.execute(select(User).where(User.id == u.id))).scalar_one()
        assert await resolve_plan_code(s, u2) == "consumer_free"


async def test_cancelled_subscription_not_used(session_factory) -> None:
    async with session_factory() as s:
        u = User(max_user_id=880005, current_mode="business", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        fut = datetime.now(UTC) + timedelta(days=10)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="business_marketer_490",
                status="cancelled",
                expires_at=fut,
            )
        )
        await s.commit()

    async with session_factory() as s:
        u2 = (await s.execute(select(User).where(User.id == u.id))).scalar_one()
        assert await resolve_plan_code(s, u2) == "business_free"
