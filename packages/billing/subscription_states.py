"""Константы состояний подписки M7 (жизненный цикл + рекуррент)."""

from __future__ import annotations

# Ожидание первой оплаты (редко: отдельная запись до webhook)
PENDING_ACTIVATION = "pending_activation"
ACTIVE = "active"
# Скоро списание / списание инициировано мерчантом
RENEWAL_DUE = "renewal_due"
RENEWAL_FAILED = "renewal_failed"
CANCELLED = "cancelled"
EXPIRED = "expired"

PAID_ACCESS_STATES = frozenset(
    {
        ACTIVE,
        RENEWAL_DUE,
        RENEWAL_FAILED,
        CANCELLED,
    }
)
