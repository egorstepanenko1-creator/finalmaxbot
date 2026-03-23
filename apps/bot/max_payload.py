"""
Разбор payload MAX webhook без жёсткой схемы: в доке поля эволюционируют.
См. https://dev.max.ru/docs-api/objects/Update
"""

from __future__ import annotations

from typing import Any


def _dig(d: dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def extract_update_type(update: dict[str, Any]) -> str | None:
    v = update.get("update_type")
    return str(v) if v is not None else None


def extract_sender_user_id(message: dict[str, Any]) -> int | None:
    sender = message.get("sender")
    if not isinstance(sender, dict):
        return None
    if sender.get("is_bot") is True:
        return None
    uid = sender.get("user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def extract_message_text(message: dict[str, Any]) -> str | None:
    body = message.get("body")
    if not isinstance(body, dict):
        return None
    text = body.get("text")
    if text is None:
        return None
    return str(text).strip() or None


def extract_callback(update: dict[str, Any]) -> dict[str, Any] | None:
    cb = update.get("callback")
    return cb if isinstance(cb, dict) else None


def extract_callback_id(update: dict[str, Any]) -> str | None:
    cb = extract_callback(update)
    if not cb:
        return None
    cid = cb.get("callback_id")
    return str(cid) if cid is not None else None


def extract_callback_payload(update: dict[str, Any]) -> str | None:
    cb = extract_callback(update)
    if not cb:
        return None
    p = cb.get("payload")
    return str(p) if p is not None else None


def extract_callback_user_id(update: dict[str, Any]) -> int | None:
    cb = extract_callback(update)
    if not cb:
        return None
    user = cb.get("user")
    if isinstance(user, dict) and user.get("user_id") is not None:
        try:
            return int(user["user_id"])
        except (TypeError, ValueError):
            return None
    return extract_sender_user_id({"sender": user} if isinstance(user, dict) else {})


def extract_message_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    m = update.get("message")
    return m if isinstance(m, dict) else None


def extract_bot_started_user_id(update: dict[str, Any]) -> int | None:
    # Возможные варианты имен полей — проверяем несколько
    for path in (("user", "user_id"), ("chat", "user_id"), ("sender", "user_id")):
        uid = _dig(update, *path)
        if uid is not None:
            try:
                return int(uid)
            except (TypeError, ValueError):
                continue
    return None
