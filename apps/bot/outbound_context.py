"""Контекст исходящего MAX-сообщения: chat_id из текущего webhook (ContextVar)."""

from __future__ import annotations

import contextvars

# Выставляется в router.max_webhook на время обработки update и create_task(after_commit).
outbound_max_chat_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "outbound_max_chat_id",
    default=None,
)
