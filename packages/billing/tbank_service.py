"""Реализация оплаты через T-Bank (Tinkoff Acquiring v2) — рекуррент MIT COF Recurring."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from packages.billing import subscription_states as ss
from packages.billing.domain import CheckoutSessionResult, RecurrentPayload, SubscriptionActivation
from packages.billing.interfaces import BillingPort
from packages.billing.tbank.token import attach_token, build_tbank_token
from packages.db.models import Subscription
from packages.shared import user_copy_ru as ru

logger = logging.getLogger(__name__)

PLAN_AMOUNTS_KOPECKS = {
    "consumer_plus_290": 29_000,
    "business_marketer_490": 49_000,
    "stars_topup_99": 9_900,
}


def _short_order_id(prefix: str, user_id: int) -> str:
    """OrderId в Т-Банке ≤ 36 символов."""
    tail = uuid.uuid4().hex[:8]
    raw = f"{prefix}{user_id}-{tail}"
    return raw[:36]


class TBankBillingService(BillingPort):
    def __init__(self, settings: Any) -> None:
        self._s = settings

    def _base(self) -> str:
        return self._s.tbank_api_base.rstrip("/")

    def _customer_key(self, user_id: int) -> str:
        return f"u{user_id}"[:36]

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
                "m7_event=checkout_unknown_plan correlation_id=%s plan_code=%s",
                correlation,
                plan_code,
            )
            amount = PLAN_AMOUNTS_KOPECKS["consumer_plus_290"]
            plan_code = "consumer_plus_290"
        order_id = _short_order_id("p", user_id)
        ck = self._customer_key(user_id)
        data_obj: dict[str, str] = {
            "user_id": str(user_id),
            "plan_code": plan_code,
            "billing_kind": "subscription_initial",
            "customer_key": ck,
        }
        payload: dict[str, Any] = {
            "TerminalKey": self._s.tbank_terminal_key,
            "Amount": amount,
            "OrderId": order_id,
            "Description": self._s.tbank_payment_description_prefix + plan_code,
            "DATA": json.dumps(data_obj, ensure_ascii=False),
            "CustomerKey": ck,
        }
        if getattr(self._s, "m7_recurring_enabled", True) and plan_code in (
            "consumer_plus_290",
            "business_marketer_490",
        ):
            payload["Recurrent"] = "Y"
            payload["OperationInitiatorType"] = "0"
        succ = success_return_url or self._s.tbank_success_url
        if succ:
            payload["SuccessURL"] = succ
        if self._s.tbank_notification_url:
            payload["NotificationURL"] = self._s.tbank_notification_url
        payload = attach_token(payload, password=self._s.tbank_password)
        url = f"{self._base()}/Init"
        logger.info(
            "m7_event=checkout_created correlation_id=%s order_id=%s plan_code=%s recurrent=%s",
            correlation,
            order_id,
            plan_code,
            payload.get("Recurrent", ""),
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(url, json=payload)
            body = r.json()
        except Exception as e:
            logger.exception("m7_event=checkout_http_error correlation_id=%s", correlation)
            return CheckoutSessionResult(
                checkout_id=order_id,
                payment_url="",
                plan_code=plan_code,
                meta={"error": type(e).__name__, "correlation_id": correlation},
            )
        if not body.get("Success"):
            err = body.get("Message") or body.get("Details") or "init_failed"
            logger.warning(
                "m7_event=checkout_init_failed correlation_id=%s order_id=%s err=%s",
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
            "m7_event=checkout_payment_url_ok correlation_id=%s payment_id=%s order_id=%s",
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
        days = int(self._s.m6_subscription_period_days)
        expires = now + timedelta(days=days)
        rebill = recurrent.rebill_id if recurrent else None
        ck = self._customer_key(user_id)
        if recurrent and recurrent.customer_key:
            ck = recurrent.customer_key[:64]
        sub = Subscription(
            user_id=user_id,
            plan_code=plan_code,
            status="active",
            subscription_state=ss.ACTIVE,
            tbank_rebill_id=rebill,
            tbank_customer_key=ck[:64] if ck else None,
            tbank_parent_payment_id=external_payment_id,
            auto_renew_enabled=True,
            meta={
                "external_payment_id": external_payment_id,
                "provider": "tbank",
                "activated_at": now.isoformat(),
                "billing_kind": "subscription_initial",
            },
            expires_at=expires,
        )
        session.add(sub)
        await session.flush()
        logger.info(
            "m7_event=subscription_row_created user_id=%s plan=%s has_rebill=%s",
            user_id,
            plan_code,
            bool(rebill),
        )
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
        days = int(self._s.m6_subscription_period_days)
        now = datetime.now(UTC)
        anchor = sub.expires_at or now
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        base = max(anchor, now)
        sub.expires_at = base + timedelta(days=days)
        sub.subscription_state = ss.ACTIVE
        meta["last_renewal_payment_id"] = external_payment_id
        meta.pop("renewal_pending_payment_id", None)
        sub.meta = meta
        await session.flush()
        logger.info(
            "m7_event=subscription_renewed user_id=%s plan=%s payment_id=%s new_expires=%s",
            user_id,
            plan_code,
            external_payment_id,
            sub.expires_at.isoformat() if sub.expires_at else "",
        )

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
        logger.warning(
            "m7_event=renewal_failed_state user_id=%s plan=%s payment_id=%s",
            user_id,
            plan_code,
            correlation_payment_id,
        )

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
        logger.info("m7_event=auto_renew_cancelled user_id=%s", user_id)
        return changed

    async def handle_provider_webhook(self, *, payload: bytes, headers: dict[str, str]) -> str:
        _ = (payload, headers)
        return "ignored"

    def subscription_ux_message(self) -> str:
        return ru.SUBSCRIPTION_UX_LIVE

    def invite_friend_ux_message(self, *, referral_code: str) -> str:
        return ru.INVITE_FRIEND_UX.format(code=referral_code)

    def verify_notification_token(self, body: dict[str, Any]) -> bool:
        if self._s.tbank_skip_signature_verify:
            return True
        token = body.get("Token")
        if not token or not isinstance(token, str):
            return False
        expected = build_tbank_token(dict(body), password=self._s.tbank_password)
        return token.lower() == expected.lower()

    async def run_mit_renewal_charge(self, *, session: Any, sub: Subscription) -> dict[str, Any]:
        """Init (MIT R) + Charge; продление периода только после webhook."""
        if not sub.tbank_rebill_id:
            return {"ok": False, "error": "no_rebill_id"}
        if not sub.auto_renew_enabled or sub.subscription_state == ss.CANCELLED:
            return {"ok": False, "error": "renewal_disabled"}
        amount = PLAN_AMOUNTS_KOPECKS.get(sub.plan_code)
        if amount is None:
            return {"ok": False, "error": "bad_plan"}
        order_id = _short_order_id("r", sub.user_id)
        ck = sub.tbank_customer_key or self._customer_key(sub.user_id)
        data_obj = {
            "user_id": str(sub.user_id),
            "plan_code": sub.plan_code,
            "billing_kind": "subscription_renewal",
            "customer_key": ck,
        }
        init_payload: dict[str, Any] = {
            "TerminalKey": self._s.tbank_terminal_key,
            "Amount": amount,
            "OrderId": order_id,
            "Description": self._s.tbank_payment_description_prefix + "renew:" + sub.plan_code,
            "OperationInitiatorType": "R",
            "DATA": json.dumps(data_obj, ensure_ascii=False),
            "CustomerKey": ck,
        }
        if self._s.tbank_notification_url:
            init_payload["NotificationURL"] = self._s.tbank_notification_url
        init_payload = attach_token(init_payload, password=self._s.tbank_password)
        init_url = f"{self._base()}/Init"
        charge_url = f"{self._base()}/Charge"
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                ir = await client.post(init_url, json=init_payload)
                ib = ir.json()
            if not ib.get("Success"):
                await self.apply_renewal_failure(
                    session=session,
                    user_id=sub.user_id,
                    plan_code=sub.plan_code,
                    correlation_payment_id=None,
                )
                return {"ok": False, "error": ib.get("Message") or "init_failed", "stage": "init"}
            payment_id = str(ib.get("PaymentId") or "")
            if not payment_id:
                await self.apply_renewal_failure(
                    session=session,
                    user_id=sub.user_id,
                    plan_code=sub.plan_code,
                    correlation_payment_id=None,
                )
                return {"ok": False, "error": "no_payment_id", "stage": "init"}
            ch_payload: dict[str, Any] = {
                "TerminalKey": self._s.tbank_terminal_key,
                "PaymentId": payment_id,
                "RebillId": sub.tbank_rebill_id,
            }
            ch_payload = attach_token(ch_payload, password=self._s.tbank_password)
            async with httpx.AsyncClient(timeout=45.0) as client:
                cr = await client.post(charge_url, json=ch_payload)
                cb = cr.json()
            meta = sub.meta or {}
            if not cb.get("Success"):
                await self.apply_renewal_failure(
                    session=session,
                    user_id=sub.user_id,
                    plan_code=sub.plan_code,
                    correlation_payment_id=payment_id,
                )
                meta["renewal_pending_payment_id"] = None
                sub.meta = meta
                await session.flush()
                return {
                    "ok": False,
                    "error": cb.get("Message") or "charge_failed",
                    "stage": "charge",
                    "payment_id": payment_id,
                }
            sub.subscription_state = ss.RENEWAL_DUE
            meta["renewal_pending_payment_id"] = payment_id
            meta["last_renewal_init_order_id"] = order_id
            sub.meta = meta
            await session.flush()
            logger.info(
                "m7_event=renewal_charge_submitted user_id=%s order_id=%s payment_id=%s",
                sub.user_id,
                order_id,
                payment_id,
            )
            return {"ok": True, "payment_id": payment_id, "order_id": order_id}
        except Exception as e:
            logger.exception("m7_event=renewal_charge_exception user_id=%s", sub.user_id)
            await self.apply_renewal_failure(
                session=session,
                user_id=sub.user_id,
                plan_code=sub.plan_code,
                correlation_payment_id=None,
            )
            return {"ok": False, "error": type(e).__name__, "stage": "exception"}
