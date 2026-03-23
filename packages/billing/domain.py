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
