"""Обратная совместимость импортов."""

from __future__ import annotations

from packages.billing.interfaces import BillingPort
from packages.billing.stub_service import StubBillingCheckoutService

StubBillingService = StubBillingCheckoutService

__all__ = ["BillingPort", "StubBillingCheckoutService", "StubBillingService"]
