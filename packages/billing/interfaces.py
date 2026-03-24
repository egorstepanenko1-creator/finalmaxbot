"""Контракты биллинга (Т-Банк и др.) — реализации подменяемые."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from packages.billing.domain import CheckoutSessionResult, RecurrentPayload, SubscriptionActivation


@runtime_checkable
class BillingPort(Protocol):
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
        recurrent: RecurrentPayload | None = None,
    ) -> SubscriptionActivation: ...

    async def apply_successful_renewal(
        self,
        *,
        session: Any,
        user_id: int,
        plan_code: str,
        external_payment_id: str | None,
    ) -> None: ...

    async def apply_renewal_failure(
        self,
        *,
        session: Any,
        user_id: int,
        plan_code: str,
        correlation_payment_id: str | None,
    ) -> None: ...

    async def mark_subscription_expired(
        self,
        *,
        session: Any,
        user_id: int,
    ) -> bool: ...

    # cancel_subscription: отмена автопродления, доступ до expires_at
    async def cancel_subscription(self, *, session: Any, user_id: int) -> bool: ...

    async def handle_provider_webhook(self, *, payload: bytes, headers: dict[str, str]) -> str: ...

    def subscription_ux_message(self) -> str: ...

    def invite_friend_ux_message(self, *, referral_code: str) -> str: ...
