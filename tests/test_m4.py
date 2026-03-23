"""M4: квоты, paywall-решения, рефералы, ledger, идемпотентность биллинга."""

from __future__ import annotations

from sqlalchemy import func, select

from packages.billing.stub_service import StubBillingCheckoutService
from packages.db.models import StarLedgerEntry, Subscription, UsageEvent, User
from packages.entitlements.service import EntitlementService
from packages.referrals.service import ReferralService
from packages.shared.settings import Settings
from packages.stars.service import StarsLedgerService


async def _user(session, max_uid: int, mode: str | None = "consumer") -> User:
    u = User(max_user_id=max_uid, current_mode=mode, onboarding_state="mode_set")
    session.add(u)
    await session.flush()
    return u


async def test_free_consumer_image_quota_exhausted(session) -> None:
    s = Settings(
        m4_consumer_free_images_per_rolling_24h=3,
        run_alembic_on_startup=False,
        allow_runtime_create_all=False,
    )
    ent = EntitlementService(s)
    u = await _user(session, 101, "consumer")
    for _ in range(3):
        session.add(UsageEvent(user_id=u.id, kind="consumer_image_intake", units=1))
    await session.flush()
    d = await ent.can_start_consumer_image_flow(session, u)
    assert d.allowed is False
    assert d.reason == "image_quota_exhausted"
    assert d.detail["used"] == 3
    assert d.detail["limit"] == 3


async def test_greeting_shares_image_pool(session) -> None:
    s = Settings(m4_consumer_free_images_per_rolling_24h=2, run_alembic_on_startup=False)
    ent = EntitlementService(s)
    u = await _user(session, 102, "consumer")
    session.add(UsageEvent(user_id=u.id, kind="text_greeting", units=1))
    session.add(UsageEvent(user_id=u.id, kind="consumer_image_intake", units=1))
    await session.flush()
    d = await ent.can_start_consumer_greeting_flow(session, u)
    assert d.allowed is False
    assert d.reason == "image_quota_exhausted"


async def test_paywall_decision_shape_text_quota(session) -> None:
    s = Settings(m4_consumer_free_text_chats_per_rolling_24h=1, run_alembic_on_startup=False)
    ent = EntitlementService(s)
    u = await _user(session, 103, "consumer")
    session.add(UsageEvent(user_id=u.id, kind="text_question", units=1))
    await session.flush()
    d = await ent.can_complete_text_question(session, u)
    assert d.allowed is False
    assert d.reason == "text_quota_exhausted"
    assert d.plan_code == "consumer_free"
    assert d.detail["limit"] == 1


async def test_referral_reward_only_once(session) -> None:
    stars = StarsLedgerService()
    ref_svc = ReferralService(stars)
    inv = await _user(session, 201, "consumer")
    inv.referral_code = "R-TESTCODE"
    invitee = await _user(session, 202, "consumer")
    await session.flush()
    ok, msg = await ref_svc.attach_by_code(session, invitee, "R-TESTCODE")
    assert ok and msg == "ok"
    await ref_svc.try_reward_on_first_image_flow(session, invitee)
    await ref_svc.try_reward_on_first_image_flow(session, invitee)
    await session.flush()
    bal = await stars.balance_sum(session, inv.id)
    assert bal == 3
    n = (
        await session.execute(
            select(func.count()).select_from(StarLedgerEntry).where(StarLedgerEntry.user_id == inv.id)
        )
    ).scalar()
    assert n == 1


async def test_self_referral_rejected(session) -> None:
    stars = StarsLedgerService()
    ref_svc = ReferralService(stars)
    u = await _user(session, 203, "consumer")
    u.referral_code = "R-SELF123"
    await session.flush()
    ok, msg = await ref_svc.attach_by_code(session, u, "R-SELF123")
    assert ok is False
    assert msg == "self_referral"


async def test_billing_activate_idempotent_by_external_payment_id(session) -> None:
    b = StubBillingCheckoutService()
    u = await _user(session, 301, "consumer")
    await b.activate_subscription(
        session=session,
        user_id=u.id,
        plan_code="consumer_plus_290",
        external_payment_id="ext_pay_1",
    )
    await session.flush()
    c1 = (await session.execute(select(func.count()).select_from(Subscription))).scalar()
    await b.activate_subscription(
        session=session,
        user_id=u.id,
        plan_code="consumer_plus_290",
        external_payment_id="ext_pay_1",
    )
    await session.flush()
    c2 = (await session.execute(select(func.count()).select_from(Subscription))).scalar()
    assert c1 == c2 == 1


async def test_stars_ledger_balance_math(session) -> None:
    stars = StarsLedgerService()
    u = await _user(session, 401, "consumer")
    await stars.credit(
        session, user_id=u.id, delta=10, reason="a", ref_type="t", ref_id="1"
    )
    await stars.debit(session, user_id=u.id, delta=4, reason="b", ref_type="t", ref_id="2")
    await session.flush()
    assert await stars.balance_sum(session, u.id) == 6
    rows = (await session.execute(select(StarLedgerEntry).where(StarLedgerEntry.user_id == u.id))).scalars().all()
    assert sum(r.delta for r in rows) == 6
    assert rows[-1].balance_after == 6
