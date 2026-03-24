"""M7: рекуррент, продления, отмена автопродления, состояния и entitlements."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from packages.billing import subscription_states as ss
from packages.billing.stub_service import StubBillingCheckoutService
from packages.billing.webhook_logic import process_tbank_notification_json
from packages.db.models import Subscription, User
from packages.entitlements.resolver import resolve_plan_code


def _initial_body(
    *,
    user_id: int,
    payment_id: str,
    plan: str,
    rebill_id: str | None = "rebill_stub_1",
) -> dict[str, object]:
    d: dict[str, object] = {
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": payment_id,
        "OrderId": f"fm_{user_id}_legacyorder",
        "DATA": json.dumps(
            {
                "user_id": str(user_id),
                "plan_code": plan,
                "billing_kind": "subscription_initial",
                "customer_key": f"u{user_id}",
            }
        ),
        "Token": "dummy",
    }
    if rebill_id:
        d["RebillId"] = rebill_id
    return d


def _renew_body(*, user_id: int, payment_id: str, plan: str) -> dict[str, object]:
    return {
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": payment_id,
        "OrderId": f"p{user_id}-rnwabcd",
        "DATA": json.dumps(
            {
                "user_id": str(user_id),
                "plan_code": plan,
                "billing_kind": "subscription_renewal",
            }
        ),
        "Token": "dummy",
    }


async def test_first_activation_with_rebill(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=990001, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id
    body = _initial_body(user_id=uid, payment_id="pay-init-1", plan="consumer_plus_290")
    async with session_factory() as s:
        res = await process_tbank_notification_json(
            session=s,
            body=body,
            billing=billing,
            verify_token=lambda _b: True,
        )
    assert res.reason == "activated"
    assert res.max_notice == "activated_initial"
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.user_id == uid, Subscription.status == "active"))
        ).scalars().first()
        assert sub is not None
        assert sub.tbank_rebill_id == "rebill_stub_1"


async def test_duplicate_activation_callback(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=990002, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        uid = u.id
    body = _initial_body(user_id=uid, payment_id="pay-dup-act", plan="consumer_plus_290")
    async with session_factory() as s:
        r1 = await process_tbank_notification_json(
            session=s, body=body, billing=billing, verify_token=lambda _b: True
        )
    async with session_factory() as s:
        r2 = await process_tbank_notification_json(
            session=s, body=body, billing=billing, verify_token=lambda _b: True
        )
    assert r1.reason == "activated"
    assert r2.reason == "duplicate"


async def test_recurring_renewal_success(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=990003, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        anchor = datetime.now(UTC) + timedelta(days=5)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                subscription_state=ss.ACTIVE,
                expires_at=anchor,
                tbank_rebill_id="r1",
                auto_renew_enabled=True,
            )
        )
        await s.commit()
        uid = u.id
    body = _renew_body(user_id=uid, payment_id="pay-renew-ok", plan="consumer_plus_290")
    async with session_factory() as s:
        res = await process_tbank_notification_json(
            session=s, body=body, billing=billing, verify_token=lambda _b: True
        )
    assert res.reason == "renewed"
    assert res.max_notice == "subscription_renewed"
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.user_id == uid, Subscription.status == "active"))
        ).scalars().first()
        assert sub is not None
        assert sub.subscription_state == ss.ACTIVE
        assert sub.expires_at is not None
        new_exp = sub.expires_at
        if new_exp.tzinfo is None:
            new_exp = new_exp.replace(tzinfo=UTC)
        anch = anchor if anchor.tzinfo else anchor.replace(tzinfo=UTC)
        assert new_exp > anch


async def test_recurring_renewal_failure(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=990004, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        fut = datetime.now(UTC) + timedelta(days=3)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                subscription_state=ss.ACTIVE,
                expires_at=fut,
                tbank_rebill_id="r1",
            )
        )
        await s.commit()
        uid = u.id
    body = {
        "Success": False,
        "Status": "REJECTED",
        "PaymentId": "pay-renew-fail",
        "OrderId": f"p{uid}-fail",
        "DATA": json.dumps(
            {
                "user_id": str(uid),
                "plan_code": "consumer_plus_290",
                "billing_kind": "subscription_renewal",
            }
        ),
        "Token": "d",
    }
    async with session_factory() as s:
        res = await process_tbank_notification_json(
            session=s, body=body, billing=billing, verify_token=lambda _b: True
        )
    assert res.reason == "renewal_failed"
    assert res.max_notice == "renewal_failed"
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.user_id == uid, Subscription.status == "active"))
        ).scalars().first()
        assert sub is not None
        assert sub.subscription_state == ss.RENEWAL_FAILED


async def test_cancel_auto_renew_keeps_entitlements_until_expiry(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=990005, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        fut = datetime.now(UTC) + timedelta(days=7)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                subscription_state=ss.ACTIVE,
                expires_at=fut,
                auto_renew_enabled=True,
            )
        )
        await s.commit()
        uid = u.id
    async with session_factory() as s:
        u2 = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        assert await resolve_plan_code(s, u2) == "consumer_plus_290"
        ok = await billing.cancel_subscription(session=s, user_id=uid)
        assert ok is True
        await s.commit()
    async with session_factory() as s:
        u3 = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        assert await resolve_plan_code(s, u3) == "consumer_plus_290"
        sub = (
            await s.execute(select(Subscription).where(Subscription.user_id == uid, Subscription.status == "active"))
        ).scalars().first()
        assert sub.subscription_state == ss.CANCELLED
        assert sub.auto_renew_enabled is False


async def test_expiry_fallback_after_mark_expired(session_factory) -> None:
    billing = StubBillingCheckoutService()
    async with session_factory() as s:
        u = User(max_user_id=990006, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        past = datetime.now(UTC) - timedelta(hours=1)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                subscription_state=ss.ACTIVE,
                expires_at=past,
            )
        )
        await s.commit()
        uid = u.id
    async with session_factory() as s:
        changed = await billing.mark_subscription_expired(session=s, user_id=uid)
        assert changed is True
        await s.commit()
    async with session_factory() as s:
        u2 = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        assert await resolve_plan_code(s, u2) == "consumer_free"


@pytest.mark.parametrize(
    ("state", "expected_plus", "max_uid"),
    [
        (ss.ACTIVE, True, 991001),
        (ss.RENEWAL_DUE, True, 991002),
        (ss.RENEWAL_FAILED, True, 991003),
        (ss.CANCELLED, True, 991004),
        (ss.PENDING_ACTIVATION, False, 991005),
        (ss.EXPIRED, False, 991006),
    ],
)
async def test_entitlement_by_subscription_state(
    session_factory, state: str, expected_plus: bool, max_uid: int
) -> None:
    async with session_factory() as s:
        u = User(max_user_id=max_uid, current_mode="consumer", onboarding_state="mode_set")
        s.add(u)
        await s.flush()
        fut = datetime.now(UTC) + timedelta(days=10)
        s.add(
            Subscription(
                user_id=u.id,
                plan_code="consumer_plus_290",
                status="active",
                subscription_state=state,
                expires_at=fut,
            )
        )
        await s.commit()
        u2 = (await s.execute(select(User).where(User.id == u.id))).scalar_one()
        got = await resolve_plan_code(s, u2)
        if expected_plus:
            assert got == "consumer_plus_290"
        else:
            assert got == "consumer_free"
