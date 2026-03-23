"""Обратная совместимость импортов + UX-заглушки."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from packages.billing.stub_service import StubBillingCheckoutService

# Реэкспорт единого сервиса
StubBillingService = StubBillingCheckoutService


@runtime_checkable
class BillingPort(Protocol):
    def subscription_ux_message(self) -> str: ...
    def invite_friend_ux_message(self, *, referral_code: str) -> str: ...
