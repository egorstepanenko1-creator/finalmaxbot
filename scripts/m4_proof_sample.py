"""Одноразовый скрипт: заполняет SQLite и печатает строки для отчёта M4."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from packages.billing.stub_service import StubBillingCheckoutService
from packages.db import models  # noqa: F401
from packages.db.base import Base
from packages.db.models import UsageEvent, User
from packages.entitlements.service import EntitlementService
from packages.referrals.service import ReferralService
from packages.shared.settings import Settings
from packages.stars.service import StarsLedgerService


async def _run() -> None:
    db = Path(__file__).resolve().parents[1] / "m4_proof.db"
    db.unlink(missing_ok=True)
    url = f"sqlite+aiosqlite:///{db.as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fac = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        run_alembic_on_startup=False,
        allow_runtime_create_all=False,
        m4_consumer_free_images_per_rolling_24h=3,
    )
    ent = EntitlementService(settings)
    billing = StubBillingCheckoutService()
    stars = StarsLedgerService()
    ref_svc = ReferralService(stars)

    async with fac() as session:
        u_quota = User(max_user_id=9001, current_mode="consumer", onboarding_state="mode_set")
        session.add(u_quota)
        await session.flush()
        for _ in range(3):
            session.add(UsageEvent(user_id=u_quota.id, kind="consumer_image_intake", units=1))
        await session.flush()
        exhausted = await ent.can_start_consumer_image_flow(session, u_quota)

        u_sub = User(max_user_id=9004, current_mode="consumer", onboarding_state="mode_set")
        session.add(u_sub)
        await session.flush()
        await billing.activate_subscription(
            session=session,
            user_id=u_sub.id,
            plan_code="consumer_plus_290",
            external_payment_id="proof_pay_1",
        )

        inv = User(
            max_user_id=9002,
            current_mode="consumer",
            onboarding_state="mode_set",
            referral_code="R-PROOF01",
        )
        invitee = User(max_user_id=9003, current_mode="consumer", onboarding_state="mode_set")
        session.add(inv)
        session.add(invitee)
        await session.flush()
        await ref_svc.attach_by_code(session, invitee, "R-PROOF01")
        session.add(UsageEvent(user_id=invitee.id, kind="consumer_image_intake", units=1))
        await session.flush()
        await ref_svc.try_reward_on_first_image_flow(session, invitee)
        await ref_svc.try_reward_on_first_image_flow(session, invitee)

        await session.commit()

    print("--- EntitlementDecision (quota exhaustion) ---")
    print(exhausted)
    print("--- SQLite rows (usage_events user 9001) ---")
    con = sqlite3.connect(db)
    q_usage = (
        "SELECT id, user_id, kind, units FROM usage_events "
        "WHERE user_id = (SELECT id FROM users WHERE max_user_id = 9001)"
    )
    for row in con.execute(q_usage):
        print(row)
    print("--- subscriptions (user 9004) ---")
    q_sub = (
        "SELECT id, user_id, plan_code, status FROM subscriptions "
        "WHERE user_id = (SELECT id FROM users WHERE max_user_id = 9004)"
    )
    for row in con.execute(q_sub):
        print(row)
    print("--- referrals ---")
    for row in con.execute("SELECT id, inviter_user_id, invitee_user_id, status FROM referrals"):
        print(row)
    print("--- stars_ledger ---")
    for row in con.execute("SELECT id, user_id, delta, reason, ref_type, ref_id, balance_after FROM stars_ledger"):
        print(row)
    con.close()


if __name__ == "__main__":
    asyncio.run(_run())
