"""
Локальная симуляция цепочки MAX webhook для M3 (без реального MAX).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UID = 900_001


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8765")
    args = p.parse_args()
    base = args.base.rstrip("/")

    steps = [
        (
            "bot_started",
            {
                "update_type": "bot_started",
                "timestamp": 1700000000,
                "user": {"user_id": UID, "is_bot": False, "first_name": "Тест"},
            },
        ),
        (
            "mode_consumer",
            {
                "update_type": "message_callback",
                "timestamp": 1700000001,
                "callback": {
                    "callback_id": "cb-mode-1",
                    "payload": "v1|mode|consumer",
                    "user": {"user_id": UID, "is_bot": False},
                },
            },
        ),
        (
            "ask_question_btn",
            {
                "update_type": "message_callback",
                "timestamp": 1700000002,
                "callback": {
                    "callback_id": "cb-ask-1",
                    "payload": "v1|consumer|ask_question",
                    "user": {"user_id": UID, "is_bot": False},
                },
            },
        ),
        (
            "question_text",
            {
                "update_type": "message_created",
                "timestamp": 1700000003,
                "message": {
                    "sender": {"user_id": UID, "is_bot": False, "first_name": "Тест"},
                    "recipient": {},
                    "timestamp": 1700000003,
                    "body": {"mid": "m-sim-1", "text": "Объясни одной фразой, что такое облако."},
                },
            },
        ),
        (
            "image_btn",
            {
                "update_type": "message_callback",
                "timestamp": 1700000004,
                "callback": {
                    "callback_id": "cb-img-1",
                    "payload": "v1|consumer|create_image",
                    "user": {"user_id": UID, "is_bot": False},
                },
            },
        ),
        (
            "image_prompt",
            {
                "update_type": "message_created",
                "timestamp": 1700000005,
                "message": {
                    "sender": {"user_id": UID, "is_bot": False, "first_name": "Тест"},
                    "recipient": {},
                    "timestamp": 1700000005,
                    "body": {"mid": "m-sim-2", "text": "Закат над морем, тёплые тона, без людей."},
                },
            },
        ),
    ]

    with httpx.Client(timeout=30.0) as client:
        for name, body in steps:
            r = client.post(f"{base}/webhooks/max", json=body)
            print(name, r.status_code, r.text[:120])
            if r.status_code >= 400:
                return 1

    db = ROOT / "finalmaxbot.db"
    if db.exists():
        import sqlite3

        con = sqlite3.connect(db)
        cur = con.cursor()
        print("--- users ---", cur.execute("select id,max_user_id,current_mode from users").fetchall())
        print("--- conv ---", cur.execute("select user_id,flow_state from conversations").fetchall())
        print("--- usage ---", cur.execute("select kind from usage_events").fetchall())
        print("--- jobs ---", cur.execute("select id,status,prompt from generation_jobs").fetchall())
        print("--- raw webhook count ---", cur.execute("select count(*) from webhook_raw_events").fetchone())
        print("--- processed ---", cur.execute("select idempotency_key from webhook_processed").fetchall())
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
