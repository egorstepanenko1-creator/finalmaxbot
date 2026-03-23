from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.bot.max_payload import (
    extract_bot_started_user_id,
    extract_callback,
    extract_message_from_update,
    extract_sender_user_id,
    extract_update_type,
)


def compute_idempotency_key(update: dict[str, Any]) -> str:
    """
    Идемпотентность: update_id от провайдера, иначе callback_id, иначе mid+user, иначе стабильный hash.
    """
    uid = update.get("update_id")
    if uid is not None and str(uid).strip() != "":
        return f"v1:upd:{uid}"

    ut = extract_update_type(update)

    if ut == "message_callback":
        cb = extract_callback(update) or {}
        cid = cb.get("callback_id")
        if cid is not None and str(cid).strip() != "":
            return f"v1:cb:{cid}"

    if ut == "message_created":
        msg = extract_message_from_update(update) or {}
        body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
        mid = body.get("mid")
        sender = extract_sender_user_id(msg)
        ts = msg.get("timestamp")
        if mid is not None and str(mid).strip() != "":
            return f"v1:msg:{sender}:{mid}"
        text = body.get("text") if isinstance(body, dict) else None
        h = hashlib.sha256(
            json.dumps({"t": text, "ts": ts, "s": sender}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
        return f"v1:msg:fallback:{sender}:{ts}:{h}"

    if ut == "bot_started":
        bu = extract_bot_started_user_id(update)
        ts = update.get("timestamp")
        return f"v1:start:{bu}:{ts}"

    blob = json.dumps(update, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return f"v1:hash:{hashlib.sha256(blob).hexdigest()}"
