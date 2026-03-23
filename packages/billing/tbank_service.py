"""Реализация оплаты через T-Bank (Tinkoff Acquiring v2) — изолированный адаптер."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from packages.billing.domain import CheckoutSessionResult, SubscriptionActivation
from packages.billing.interfaces import BillingPort
from packages.billing.tbank.token import attach_token, build_tbank_token
from packages.db.models import Subscription

logger = logging.getLogger(__name__)

PLAN_AMOUNTS_KOPECKS = {
    "consumer_plus_290": 29_000,
    "business_marketer_490": 49_000,
    "stars_topup_99": 9_900,
}


class TBankBillingService(BillingPort):
    def __init__(self, settings: Any) -> None:
        self._s = settings

    def _base(self) -> str:
        return self._s.tbank_api_base.rstrip("/")

    async def create_checkout_session(
        self,
        *,
        user_id: int,
        plan_code: str,
        success_return_url: str | None,
    ) -> CheckoutSessionResult:
        correlation = f"chk_{uuid.uuid4().hex[:16]}"
        amount = PLAN_AMOUNTS_KOPECKS.get(plan_code)
        if amount is None:
            logger.warning(
                "m6_event=checkout_unknown_plan correlation_id=%s plan_code=%s",
                correlation,
                plan_code,
            )
            amount = PLAN_AMOUNTS_KOPECKS["consumer_plus_290"]
            plan_code = "consumer_plus_290"
        order_id = f"fm_{user_id}_{uuid.uuid4().hex[:12]}"
        data_obj = {"user_id": str(user_id), "plan_code": plan_code}
        payload: dict[str, Any] = {
            "TerminalKey": self._s.tbank_terminal_key,
            "Amount": amount,
            "OrderId": order_id,
            "Description": self._s.tbank_payment_description_prefix + plan_code,
            "DATA": json.dumps(data_obj, ensure_ascii=False),
        }
        succ = success_return_url or self._s.tbank_success_url
        if succ:
            payload["SuccessURL"] = succ
        if self._s.tbank_notification_url:
            payload["NotificationURL"] = self._s.tbank_notification_url
        payload = attach_token(payload, password=self._s.tbank_password)
        url = f"{self._base()}/Init"
        logger.info(
            "m6_event=checkout_created correlation_id=%s order_id=%s plan_code=%s amount_kop=%s",
            correlation,
            order_id,
            plan_code,
            amount,
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload)
            body = r.json()
        except Exception as e:
            logger.exception("m6_event=checkout_http_error correlation_id=%s", correlation)
            return CheckoutSessionResult(
                checkout_id=order_id,
                payment_url="",
                plan_code=plan_code,
                meta={"error": type(e).__name__, "correlation_id": correlation},
            )
        if not body.get("Success"):
            err = body.get("Message") or body.get("Details") or "init_failed"
            logger.warning(
                "m6_event=checkout_init_failed correlation_id=%s order_id=%s err=%s",
                correlation,
                order_id,
                str(err)[:200],
            )
            return CheckoutSessionResult(
                checkout_id=order_id,
                payment_url="",
                plan_code=plan_code,
                meta={"error": str(err)[:500], "correlation_id": correlation},
            )
        pay_url = body.get("PaymentURL") or ""
        pid = str(body.get("PaymentId") or "")
        logger.info(
            "m6_event=checkout_payment_url_ok correlation_id=%s payment_id=%s order_id=%s",
            correlation,
            pid,
            order_id,
        )
        return CheckoutSessionResult(
            checkout_id=order_id,
            payment_url=pay_url,
            plan_code=plan_code,
            meta={
                "payment_id": pid,
                "correlation_id": correlation,
                "amount_kopecks": amount,
            },
        )

    async def create_stars_topup_checkout(
        self,
        *,
        user_id: int,
        success_return_url: str | None = None,
    ) -> CheckoutSessionResult:
        """Разовое пополнение звёзд (заглушка суммы stars_topup_99)."""
        return await self.create_checkout_session(
            user_id=user_id,
            plan_code="stars_topup_99",
            success_return_url=success_return_url,
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
        days = int(self._s.m6_subscription_period_days)
        expires = now + timedelta(days=days)
        sub = Subscription(
            user_id=user_id,
            plan_code=plan_code,
            status="active",
            meta={
                "external_payment_id": external_payment_id,
                "provider": "tbank",
                "activated_at": now.isoformat(),
            },
            expires_at=expires,
        )
        session.add(sub)
        await session.flush()
        logger.debug(
            "tbank_activate user_id=%s plan_code=%s payment_id=%s expires_at=%s",
            user_id,
            plan_code,
            external_payment_id,
            expires.isoformat(),
        )
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
            "Оплата проходит на защищённой странице Т-Банка. После успешной оплаты подписка "
            "включится автоматически в течение минуты."
        )

    def invite_friend_ux_message(self, *, referral_code: str) -> str:
        return (
            "Пригласите друга в MAX: отправьте ему **код приглашения**.\n"
            f"Код: `{referral_code}`\n\n"
            "Когда друг **первый раз** сделает картинку или поздравление, вам начислят **+3★** "
            "(один раз за друга).\n"
            "Другу нужно нажать «Ввести код приглашения» и отправить код."
        )

    def verify_notification_token(self, body: dict[str, Any]) -> bool:
        if self._s.tbank_skip_signature_verify:
            return True
        token = body.get("Token")
        if not token or not isinstance(token, str):
            return False
        expected = build_tbank_token(dict(body), password=self._s.tbank_password)
        return token.lower() == expected.lower()
