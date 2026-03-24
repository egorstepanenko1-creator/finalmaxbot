"""Обработка уведомления Т-Банка: верификация, идемпотентность, активация и продления."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from packages.billing.domain import RecurrentPayload, TbankWebhookResult
from packages.billing.interfaces import BillingPort
from packages.db.models import BillingEvent, User
from packages.stars.service import StarsLedgerService

logger = logging.getLogger(__name__)

_ORDER_RE = re.compile(r"^p(\d+)-")
_ORDER_FM_RE = re.compile(r"^fm_(\d+)_")  # legacy M6 order ids
_PLUS_PLANS = frozenset({"consumer_plus_290", "business_marketer_490"})


def redact_notification_payload(body: dict[str, Any]) -> dict[str, Any]:
    red: dict[str, Any] = {}
    for k, v in body.items():
        if k == "Token":
            red[k] = "***"
        elif k in ("RebillId", "rebillId") and v is not None:
            red[k] = "***"
        elif isinstance(v, (dict, list)):
            red[k] = str(v)[:500]
        else:
            red[k] = v
    return red


def _parse_data_dict(body: dict[str, Any]) -> dict[str, Any]:
    data_raw = body.get("DATA")
    if isinstance(data_raw, str) and data_raw.strip():
        try:
            d = json.loads(data_raw)
            return d if isinstance(d, dict) else {}
        except json.JSONDecodeError:
            return {}
    if isinstance(data_raw, dict):
        return data_raw
    return {}


def _parse_user_and_plan(body: dict[str, Any]) -> tuple[int | None, str | None]:
    uid: int | None = None
    plan: str | None = None
    d = _parse_data_dict(body)
    if d:
        u = d.get("user_id")
        if u is not None:
            try:
                uid = int(u)
            except (ValueError, TypeError):
                uid = None
        p = d.get("plan_code")
        if isinstance(p, str):
            plan = p
    oid = body.get("OrderId")
    if isinstance(oid, str):
        m = _ORDER_RE.match(oid) or _ORDER_FM_RE.match(oid)
        if m:
            uid = uid or int(m.group(1))
    return uid, plan


def _parse_billing_kind(body: dict[str, Any]) -> str:
    d = _parse_data_dict(body)
    k = d.get("billing_kind")
    if k == "subscription_renewal":
        return "subscription_renewal"
    return "subscription_initial"


def _extract_rebill_id(body: dict[str, Any]) -> str | None:
    rid = body.get("RebillId") or body.get("rebillId")
    if rid is None:
        return None
    s = str(rid).strip()
    return s or None


def _is_payment_success(body: dict[str, Any]) -> bool:
    if not body.get("Success"):
        return False
    status = str(body.get("Status") or "").upper()
    return status in ("CONFIRMED", "AUTHORIZED")


def _stable_key(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


async def process_tbank_notification_json(
    *,
    session: Any,
    body: dict[str, Any],
    billing: BillingPort,
    verify_token: Any,
) -> TbankWebhookResult:
    correlation = str(body.get("OrderId") or body.get("PaymentId") or "unknown")
    safe = redact_notification_payload(dict(body))

    async def audit(
        outcome: str,
        key: str,
        uid: int | None,
        plan: str | None,
        *,
        event_type: str = "notification",
    ) -> None:
        session.add(
            BillingEvent(
                idempotency_key=key[:128],
                provider="tbank",
                event_type=event_type,
                outcome=outcome,
                order_id=str(body.get("OrderId") or "")[:128] or None,
                user_id=uid,
                plan_code=plan,
                payload_safe=safe,
            )
        )
        await session.flush()

    if not verify_token(body):
        logger.warning("m7_event=billing_callback_rejected correlation_id=%s reason=bad_token", correlation)
        key = _stable_key("token", correlation, json.dumps(safe, sort_keys=True, default=str)[:200])
        try:
            await audit("rejected_token", key, None, None)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("m7_event=billing_callback_deduplicated correlation_id=%s branch=token", correlation)
        return TbankWebhookResult(ok=True, reason="bad_token")

    payment_id = str(body.get("PaymentId") or "")
    if not payment_id:
        logger.warning("m7_event=billing_callback_rejected correlation_id=%s reason=no_payment_id", correlation)
        key = _stable_key("noid", correlation)
        try:
            await audit("rejected_no_payment_id", key, None, None)
            await session.commit()
        except IntegrityError:
            await session.rollback()
        return TbankWebhookResult(ok=True, reason="no_payment_id")

    user_id, plan_code = _parse_user_and_plan(body)
    billing_kind = _parse_billing_kind(body)

    if user_id is None or not plan_code:
        logger.warning(
            "m7_event=billing_callback_rejected correlation_id=%s reason=missing_user_or_plan",
            correlation,
        )
        key = _stable_key("parse", payment_id, correlation)
        try:
            await audit("rejected_parse", key, user_id, plan_code)
            await session.commit()
        except IntegrityError:
            await session.rollback()
        return TbankWebhookResult(ok=True, reason="parse")

    if not _is_payment_success(body):
        if billing_kind == "subscription_renewal" and plan_code in _PLUS_PLANS:
            key = f"{payment_id}:renewal_fail:{body.get('Status')}"[:128]
            try:
                await audit(
                    "renewal_payment_failed",
                    key,
                    user_id,
                    plan_code,
                    event_type="renewal_failure",
                )
                await billing.apply_renewal_failure(
                    session=session,
                    user_id=user_id,
                    plan_code=plan_code,
                    correlation_payment_id=payment_id,
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info(
                    "m7_event=billing_callback_deduplicated correlation_id=%s payment_id=%s branch=renewal_fail",
                    correlation,
                    payment_id,
                )
                return TbankWebhookResult(ok=True, reason="duplicate", user_id=user_id, plan_code=plan_code or "")
            logger.warning(
                "m7_event=renewal_payment_failed_notice correlation_id=%s user_id=%s payment_id=%s",
                correlation,
                user_id,
                payment_id,
            )
            return TbankWebhookResult(
                ok=True,
                reason="renewal_failed",
                user_id=user_id,
                max_notice="renewal_failed",
                plan_code=plan_code,
            )

        key = f"{payment_id}:ns:{body.get('Status')}"[:128]
        try:
            await audit("ignored_not_success", key, user_id, plan_code)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info(
                "m7_event=billing_callback_deduplicated correlation_id=%s payment_id=%s branch=ns",
                correlation,
                payment_id,
            )
        else:
            logger.info(
                "m7_event=billing_callback_ignored correlation_id=%s payment_id=%s status=%s",
                correlation,
                payment_id,
                body.get("Status"),
            )
        return TbankWebhookResult(ok=True, reason="not_success", user_id=user_id, plan_code=plan_code)

    processed_outcome = "processed_renewal" if billing_kind == "subscription_renewal" else "processed_initial"
    session.add(
        BillingEvent(
            idempotency_key=payment_id[:128],
            provider="tbank",
            event_type="notification",
            outcome=processed_outcome,
            order_id=str(body.get("OrderId") or "")[:128] or None,
            user_id=user_id,
            plan_code=plan_code,
            payload_safe=safe,
        )
    )
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info(
            "m7_event=billing_callback_deduplicated correlation_id=%s payment_id=%s",
            correlation,
            payment_id,
        )
        return TbankWebhookResult(ok=True, reason="duplicate", user_id=user_id, plan_code=plan_code)

    if plan_code == "stars_topup_99":
        stars = StarsLedgerService()
        await stars.credit(
            session,
            user_id=user_id,
            delta=10,
            reason="tbank_stars_topup",
            ref_type="payment",
            ref_id=payment_id,
        )
        await session.commit()
        logger.info(
            "m7_event=stars_topup_credited correlation_id=%s user_id=%s payment_id=%s",
            correlation,
            user_id,
            payment_id,
        )
        return TbankWebhookResult(ok=True, reason="stars", user_id=user_id, plan_code=plan_code)

    if billing_kind == "subscription_renewal" and plan_code in _PLUS_PLANS:
        await billing.apply_successful_renewal(
            session=session,
            user_id=user_id,
            plan_code=plan_code,
            external_payment_id=payment_id,
        )
        logger.info(
            "m7_event=subscription_renewed correlation_id=%s payment_id=%s user_id=%s plan=%s",
            correlation,
            payment_id,
            user_id,
            plan_code,
        )
        await session.commit()
        logger.info(
            "m7_event=billing_callback_processed correlation_id=%s payment_id=%s user_id=%s plan=%s",
            correlation,
            payment_id,
            user_id,
            plan_code,
        )
        return TbankWebhookResult(
            ok=True,
            reason="renewed",
            user_id=user_id,
            max_notice="subscription_renewed",
            plan_code=plan_code,
        )

    d = _parse_data_dict(body)
    ck = d.get("customer_key")
    recurrent = RecurrentPayload(
        rebill_id=_extract_rebill_id(body),
        parent_payment_id=payment_id,
        customer_key=str(ck)[:64] if ck else None,
    )
    await billing.activate_subscription(
        session=session,
        user_id=user_id,
        plan_code=plan_code,
        external_payment_id=payment_id,
        recurrent=recurrent,
    )
    logger.info(
        "m7_event=subscription_activated correlation_id=%s payment_id=%s user_id=%s plan=%s",
        correlation,
        payment_id,
        user_id,
        plan_code,
    )
    await session.commit()
    logger.info(
        "m7_event=billing_callback_processed correlation_id=%s payment_id=%s user_id=%s plan=%s",
        correlation,
        payment_id,
        user_id,
        plan_code,
    )
    return TbankWebhookResult(
        ok=True,
        reason="activated",
        user_id=user_id,
        max_notice="activated_initial",
        plan_code=plan_code,
    )


async def load_max_user_id(session: Any, internal_user_id: int) -> int | None:
    r = await session.execute(select(User.max_user_id).where(User.id == internal_user_id))
    return r.scalar_one_or_none()
