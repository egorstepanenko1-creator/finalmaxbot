"""Контракты биллинга (Т-Банк и др.) — реализации подменяемые."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from packages.billing.domain import CheckoutSessionResult, SubscriptionActivation


@runtime_checkable
class BillingCheckoutPort(Protocol):
    async def create_checkout_session(
        self,
        *,
        user_id: int,
        plan_code: str,
        success_return_url: str | None,
    ) -> CheckoutSessionResult: ...

    async def activate_subscription(
        self,
        *,
        session: Any,
        user_id: int,
        plan_code: str,
        external_payment_id: str | None,
    ) -> SubscriptionActivation: ...

    async def cancel_subscription(self, *, session: Any, user_id: int) -> bool: ...

    async def handle_provider_webhook(self, *, payload: bytes, headers: dict[str, str]) -> str:
        """Плейсхолдер: вернуть 'ignored' | 'processed'."""
        ...
