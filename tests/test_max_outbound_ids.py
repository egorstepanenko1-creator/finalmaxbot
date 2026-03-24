"""Извлечение chat_id для исходящих MAX (сверка с max-bot-mvp)."""

from __future__ import annotations

from apps.bot.max_payload import extract_outbound_max_chat_id


def test_message_created_uses_recipient_chat_id() -> None:
    upd = {
        "update_type": "message_created",
        "message": {
            "recipient": {"chat_id": -100000000, "chat_type": "dialog", "user_id": 12345},
            "sender": {"user_id": 54321, "is_bot": False},
            "body": {"mid": "m1", "text": "hi"},
        },
    }
    assert extract_outbound_max_chat_id(upd) == -100000000


def test_message_callback_chat_id_from_recipient() -> None:
    upd = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb1",
            "payload": "x",
            "user": {"user_id": 99, "is_bot": False},
        },
        "message": {"recipient": {"chat_id": 42}},
    }
    assert extract_outbound_max_chat_id(upd) == 42


def test_bot_started_no_chat_id() -> None:
    upd = {
        "update_type": "bot_started",
        "user": {"user_id": 1, "first_name": "A"},
    }
    assert extract_outbound_max_chat_id(upd) is None
