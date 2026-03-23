"""Обработка уведомления Т-Банка: верификация, идемпотентность, активация."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from packages.billing.interfaces import BillingPort
from packages.db.models import BillingEvent, User
from packages.stars.service import StarsLedgerService

logger = logging.getLogger(__name__)

_ORDER_RE = re.compile(r"^fm_(\d+)_")


def redact_notification_payload(body: dict[str, Any]) -> dict[str, Any]:
    red: dict[str, Any] = {}
    for k, v in body.items():
        if k == "Token":
            red[k] = "***"
        elif isinstance(v, (dict, list)):
            red[k] = str(v)[:500]
        else:
            red[k] = v
    return red


def _parse_user_and_plan(body: dict[str, Any]) -> tuple[int | None, str | None]:
    uid: int | None = None
    plan: str | None = None
    data_raw = body.get("DATA")
    if isinstance(data_raw, str) and data_raw.strip():
        try:
            d = json.loads(data_raw)
            if isinstance(d, dict):
                u = d.get("user_id")
                if u is not None:
                    uid = int(u)
                p = d.get("plan_code")
                if isinstance(p, str):
                    plan = p
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    oid = body.get("OrderId")
    if isinstance(oid, str):
        m = _ORDER_RE.match(oid)
        if m:
            uid = uid or int(m.group(1))
    return uid, plan


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
) -> tuple[bool, str, int | None]:
    """
    (http_ok, reason, internal_user_id_for_max_notice).
    internal_user_id только при успешной активации подписки (не stars).
    """
    correlation = str(body.get("OrderId") or body.get("PaymentId") or "unknown")
    safe = redact_notification_payload(dict(body))

    async def audit(outcome: str, key: str, uid: int | None, plan: str | None) -> None:
        session.add(
            BillingEvent(
                idempotency_key=key[:128],
                provider="tbank",
                event_type="notification",
                outcome=outcome,
                order_id=str(body.get("OrderId") or "")[:128] or None,
                user_id=uid,
                plan_code=plan,
                payload_safe=safe,
            )
        )
        await session.flush()

    if not verify_token(body):
        logger.warning("m6_event=billing_callback_rejected correlation_id=%s reason=bad_token", correlation)
        key = _stable_key("token", correlation, json.dumps(safe, sort_keys=True, default=str)[:200])
        try:
            await audit("rejected_token", key, None, None)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("m6_event=billing_callback_deduplicated correlation_id=%s branch=token", correlation)
        return True, "bad_token", None

    payment_id = str(body.get("PaymentId") or "")
    if not payment_id:
        logger.warning("m6_event=billing_callback_rejected correlation_id=%s reason=no_payment_id", correlation)
        key = _stable_key("noid", correlation)
        try:
            await audit("rejected_no_payment_id", key, None, None)
            await session.commit()
        except IntegrityError:
            await session.rollback()
        return True, "no_payment_id", None

    user_id, plan_code = _parse_user_and_plan(body)
    if user_id is None or not plan_code:
        logger.warning(
            "m6_event=billing_callback_rejected correlation_id=%s reason=missing_user_or_plan",
            correlation,
        )
        key = _stable_key("parse", payment_id, correlation)
        try:
            await audit("rejected_parse", key, user_id, plan_code)
            await session.commit()
        except IntegrityError:
            await session.rollback()
        return True, "parse", None

    if not _is_payment_success(body):
        key = f"{payment_id}:ns:{body.get('Status')}"[:128]
        try:
            await audit("ignored_not_success", key, user_id, plan_code)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info(
                "m6_event=billing_callback_deduplicated correlation_id=%s payment_id=%s branch=ns",
                correlation,
                payment_id,
            )
        else:
            logger.info(
                "m6_event=billing_callback_ignored correlation_id=%s payment_id=%s status=%s",
                correlation,
                payment_id,
                body.get("Status"),
            )
        return True, "not_success", None

    session.add(
        BillingEvent(
            idempotency_key=payment_id[:128],
            provider="tbank",
            event_type="notification",
            outcome="processed",
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
            "m6_event=billing_callback_deduplicated correlation_id=%s payment_id=%s",
            correlation,
            payment_id,
        )
        return True, "duplicate", None

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
            "m6_event=stars_topup_credited correlation_id=%s user_id=%s payment_id=%s",
            correlation,
            user_id,
            payment_id,
        )
        return True, "stars", None

    await billing.activate_subscription(
        session=session,
        user_id=user_id,
        plan_code=plan_code,
        external_payment_id=payment_id,
    )
    logger.info(
        "m6_event=subscription_activated correlation_id=%s payment_id=%s user_id=%s plan=%s",
        correlation,
        payment_id,
        user_id,
        plan_code,
    )
    await session.commit()
    logger.info(
        "m6_event=billing_callback_processed correlation_id=%s payment_id=%s user_id=%s plan=%s",
        correlation,
        payment_id,
        user_id,
        plan_code,
    )
    return True, "activated", user_id


async def load_max_user_id(session: Any, internal_user_id: int) -> int | None:
    r = await session.execute(select(User.max_user_id).where(User.id == internal_user_id))
    return r.scalar_one_or_none()
