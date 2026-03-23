"""Заглушка биллинга с реальными сигнатурами интерфейса."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from packages.billing.domain import CheckoutSessionResult, SubscriptionActivation
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
    ) -> SubscriptionActivation:
        if external_payment_id:
            r0 = await session.execute(select(Subscription).where(Subscription.user_id == user_id))
            for existing in r0.scalars():
                meta = existing.meta or {}
                if meta.get("external_payment_id") == external_payment_id:
                    return SubscriptionActivation(
                        user_id=user_id,
                        plan_code=existing.plan_code,
                        status=existing.status,
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

        now = datetime.now(UTC)
        expires = now + timedelta(days=3650)
        sub = Subscription(
            user_id=user_id,
            plan_code=plan_code,
            status="active",
            meta={"external_payment_id": external_payment_id, "stub": True},
            expires_at=expires,
        )
        session.add(sub)
        await session.flush()
        return SubscriptionActivation(
            user_id=user_id,
            plan_code=plan_code,
            status="active",
            external_id=external_payment_id,
            activated_at=now,
        )

    async def cancel_subscription(self, *, session: Any, user_id: int) -> bool:
        r = await session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
            )
        )
        changed = False
        for sub in r.scalars():
            sub.status = "cancelled"
            changed = True
        await session.flush()
        return changed

    async def handle_provider_webhook(self, *, payload: bytes, headers: dict[str, str]) -> str:
        _ = (payload, headers)
        return "ignored"


    def subscription_ux_message(self) -> str:
        return (
            "Оплата проходит на защищённой странице (в staging — тестовая ссылка-заглушка).\n"
            "После настройки Т-Банка здесь будет реальная ссылка на оплату."
        )

    def invite_friend_ux_message(self, *, referral_code: str) -> str:
        return (
            "Пригласите друга в MAX: отправьте ему этот **код приглашения**.\n"
            f"Код: `{referral_code}`\n\n"
            "Когда друг **первый раз** оформит заявку на картинку (или поздравление с квотой картинки), "
            "вам начислят **+3 звезды** (один раз за друга).\n"
            "Другу нужно нажать «Ввести код приглашения» и отправить код."
        )
