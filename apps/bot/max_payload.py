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


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _chat_id_from_message(message: dict[str, Any]) -> int | None:
    """Как в max-bot-mvp: recipient.chat_id приоритетен для POST /messages."""
    rec = message.get("recipient")
    if isinstance(rec, dict):
        got = _int_or_none(rec.get("chat_id"))
        if got is not None:
            return got
    got = _int_or_none(message.get("chat_id"))
    if got is not None:
        return got
    ch = message.get("chat")
    if isinstance(ch, dict):
        return _int_or_none(ch.get("chat_id"))
    return None


def _chat_id_from_callback_update(update: dict[str, Any]) -> int | None:
    for cid in (
        update.get("chat_id"),
        _dig(update, "message", "recipient", "chat_id"),
        _dig(update, "recipient", "chat_id"),
        _dig(update, "payload", "chat_id"),
    ):
        got = _int_or_none(cid)
        if got is not None:
            return got
    return None


def extract_outbound_max_chat_id(update: dict[str, Any]) -> int | None:
    """
    Идентификатор чата для platform-api: ?chat_id= (предпочтительно) vs ?user_id=.
    Сверено с max-bot-mvp extractMessage / extractCallback + getTarget.
    """
    ut = extract_update_type(update)
    if ut == "message_created":
        msg = extract_message_from_update(update)
        if isinstance(msg, dict):
            return _chat_id_from_message(msg)
        return None
    if ut == "message_callback":
        return _chat_id_from_callback_update(update)
    return None
