"""Заглушка биллинга с реальными сигнатурами интерфейса."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from packages.billing import subscription_states as ss
from packages.billing.domain import CheckoutSessionResult, RecurrentPayload, SubscriptionActivation
from packages.billing.interfaces import BillingPort
from packages.db.models import Subscription


class StubBillingCheckoutService(BillingPort):
    async def create_checkout_session(
        self,
        *,
        user_id: int,
        plan_code: str,
        success_return_url: str | None,
    ) -> CheckoutSessionResult:
        cid = f"chk_stub_{uuid.uuid4().hex[:12]}"
        return CheckoutSessionResult(
            checkout_id=cid,
            payment_url=f"https://stub-payments.example/checkout/{cid}",
            plan_code=plan_code,
            meta={"user_id": user_id, "return": success_return_url},
        )

    async def activate_subscription(
        self,
        *,
        session: Any,
        user_id: int,
        plan_code: str,
        external_payment_id: str | None,
        recurrent: RecurrentPayload | None = None,
    ) -> SubscriptionActivation:
        if external_payment_id:
            r0 = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
            for existing in r0.scalars():
                meta = existing.meta or {}
                if meta.get("external_payment_id") == external_payment_id:
                    return SubscriptionActivation(
                        user_id=user_id,
                        plan_code=existing.plan_code,
                        status=existing.subscription_state,
                        external_id=external_payment_id,
                        activated_at=existing.created_at,
                    )
        r = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
            )
        )
        for sub in r.scalars():
            sub.status = "superseded"
            sub.subscription_state = ss.EXPIRED

        now = datetime.now(UTC)
        expires = now + timedelta(days=3650)
        meta: dict[str, Any] = {
            "external_payment_id": external_payment_id,
            "stub": True,
            "billing_kind": "subscription_initial",
        }
        if recurrent:
            meta["stub_rebill_id"] = recurrent.rebill_id
            meta["stub_customer_key"] = recurrent.customer_key
        ck = (recurrent.customer_key if recurrent and recurrent.customer_key else f"u{user_id}")[:64]
        sub = Subscription(
            user_id=user_id,
            plan_code=plan_code,
            status="active",
            subscription_state=ss.ACTIVE,
            tbank_rebill_id=(recurrent.rebill_id if recurrent else None) or f"stub_rebill_{user_id}",
            tbank_customer_key=ck,
            tbank_parent_payment_id=external_payment_id,
            auto_renew_enabled=True,
            meta=meta,
            expires_at=expires,
        )
        session.add(sub)
        await session.flush()
        return SubscriptionActivation(
            user_id=user_id,
            plan_code=plan_code,
            status=sub.subscription_state,
            external_id=external_payment_id,
            activated_at=now,
        )

    async def apply_successful_renewal(
        self,
        *,
        session: Any,
        user_id: int,
        plan_code: str,
        external_payment_id: str | None,
    ) -> None:
        r = await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.plan_code == plan_code,
            )
            .order_by(Subscription.id.desc())
            .limit(1)
        )
        sub = r.scalars().first()
        if sub is None:
            return
        meta = sub.meta or {}
        if external_payment_id and meta.get("last_renewal_payment_id") == external_payment_id:
            return
        now = datetime.now(UTC)
        anchor = sub.expires_at or now
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        base = max(anchor, now)
        sub.expires_at = base + timedelta(days=30)
        sub.subscription_state = ss.ACTIVE
        meta["last_renewal_payment_id"] = external_payment_id
        meta.pop("renewal_pending_payment_id", None)
        sub.meta = meta
        await session.flush()

    async def apply_renewal_failure(
        self,
        *,
        session: Any,
        user_id: int,
        plan_code: str,
        correlation_payment_id: str | None,
    ) -> None:
        r = await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.plan_code == plan_code,
            )
            .order_by(Subscription.id.desc())
            .limit(1)
        )
        sub = r.scalars().first()
        if sub is None:
            return
        sub.subscription_state = ss.RENEWAL_FAILED
        meta = sub.meta or {}
        meta["last_renewal_failure_at"] = datetime.now(UTC).isoformat()
        meta["last_renewal_failure_payment_id"] = correlation_payment_id
        meta.pop("renewal_pending_payment_id", None)
        sub.meta = meta
        await session.flush()

    async def mark_subscription_expired(
        self,
        *,
        session: Any,
        user_id: int,
    ) -> bool:
        now = datetime.now(UTC)
        r = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.plan_code.in_(("consumer_plus_290", "business_marketer_490")),
            )
        )
        changed = False
        for sub in r.scalars():
            if sub.expires_at is None:
                continue
            exp = sub.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp >= now:
                continue
            sub.status = "superseded"
            sub.subscription_state = ss.EXPIRED
            changed = True
        await session.flush()
        return changed

    async def cancel_subscription(self, *, session: Any, user_id: int) -> bool:
        r = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.plan_code.in_(("consumer_plus_290", "business_marketer_490")),
            )
        )
        changed = False
        now = datetime.now(UTC)
        for sub in r.scalars():
            if sub.subscription_state == ss.CANCELLED:
                continue
            sub.auto_renew_enabled = False
            sub.subscription_state = ss.CANCELLED
            sub.cancelled_at = now
            changed = True
        await session.flush()
        return changed

    async def handle_provider_webhook(self, *, payload: bytes, headers: dict[str, str]) -> str:
        _ = (payload, headers)
        return "ignored"

    def subscription_ux_message(self) -> str:
        return (
            "Оплата проходит на защищённой странице (в staging — тестовая ссылка-заглушка).\n"
            "В бою подключится **автопродление** по модели Т-Банка (родительская оплата + RebillId + Charge)."
        )

    def invite_friend_ux_message(self, *, referral_code: str) -> str:
        return (
            "Пригласите друга в MAX: отправьте ему **код приглашения**.\n"
            f"Код: `{referral_code}`\n\n"
            "Когда друг **первый раз** оформит заявку на картинку (или поздравление с квотой картинки), "
            "вам начислят **+3 звезды** (один раз за друга).\n"
            "Другу нужно нажать «Ввести код приглашения» и отправить код."
        )
