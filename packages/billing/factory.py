"""Выбор реализации биллинга по настройкам."""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.billing.interfaces import BillingPort
from packages.billing.stub_service import StubBillingCheckoutService

if TYPE_CHECKING:
    from packages.shared.settings import Settings


def get_billing_service(settings: Settings) -> BillingPort:
    if settings.tbank_terminal_key and settings.tbank_password:
        from packages.billing.tbank_service import TBankBillingService

        return TBankBillingService(settings)
    return StubBillingCheckoutService()
