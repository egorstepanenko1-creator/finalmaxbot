"""Уведомления MAX о подписке — тексты из packages.shared.user_copy_ru."""

from __future__ import annotations

from packages.shared import user_copy_ru as ru


def notice_subscription_activated(*, plan_code: str) -> str:
    if plan_code == "business_marketer_490":
        return ru.NOTICE_PAYMENT_SUCCESS_BUSINESS
    return ru.NOTICE_PAYMENT_SUCCESS_CONSUMER


def notice_subscription_renewed(*, plan_code: str) -> str:
    _ = plan_code
    return ru.NOTICE_SUBSCRIPTION_RENEWED


def notice_renewal_failed() -> str:
    return ru.NOTICE_RENEWAL_FAILED


def notice_first_payment_failed() -> str:
    return ru.NOTICE_FIRST_PAYMENT_FAILED


def notice_subscription_cancelled() -> str:
    return ru.NOTICE_AUTORENEW_CANCELLED


def notice_access_expired() -> str:
    return ru.NOTICE_SUBSCRIPTION_EXPIRED
