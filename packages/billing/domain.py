from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CheckoutSessionResult:
    """Результат создания сессии оплаты (заглушка до Т-Банка)."""

    checkout_id: str
    payment_url: str
    plan_code: str
    meta: dict[str, Any]


@dataclass
class SubscriptionActivation:
    user_id: int
    plan_code: str
    status: str
    external_id: str | None
    activated_at: datetime


@dataclass
class RecurrentPayload:
    """Идентификаторы рекуррентной оплаты Т-Банка (не PAN/CVV)."""

    rebill_id: str | None = None
    parent_payment_id: str | None = None
    customer_key: str | None = None


@dataclass(frozen=True)
class TbankWebhookResult:
    """Результат разбора уведомления (для MAX и логов)."""

    ok: bool
    reason: str
    user_id: int | None = None
    max_notice: str = ""  # "", activated_initial, subscription_renewed, renewal_failed, access_expired
    plan_code: str = ""
