"""
Симуляция MAX webhook → тот же код, что в бою (state machine + оркестратор).

Для live-смоука с исходящими в MAX:
  set MAX_OUTBOUND_ENABLED=true в .env
  python scripts/m3_webhook_simulate.py --uid <ваш_max_user_id> --base http://127.0.0.1:8000 --flow image
  python scripts/m3_webhook_simulate.py --uid <id> --flow greeting
  python scripts/m3_webhook_simulate.py --uid <id> --flow both

Идempotency: все update_id / callback_id / mid уникальны (uuid).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pg_sync_url() -> str | None:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw or "sqlite" in raw:
        return None
    u = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    if not u.startswith("postgresql://"):
        return None
    return u.replace("ssl=require", "sslmode=require")


def _poll_db(label: str) -> None:
    url = _pg_sync_url()
    if not url:
        print(f"--- {label}: пропуск (нет Postgres DATABASE_URL или sqlite) ---")
        return
    try:
        import psycopg2
    except ImportError:
        print(f"--- {label}: установите psycopg2-binary для опроса БД ---")
        return
    try:
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, status, provider, context_kind, left(error_message, 80)
            FROM generation_jobs ORDER BY id DESC LIMIT 8
            """
        )
        print(f"--- {label}: generation_jobs ---")
        for row in cur.fetchall():
            print(row)
        cur.execute(
            """
            SELECT id, generation_job_id, byte_size, mime_type, left(storage_key, 60)
            FROM stored_files ORDER BY id DESC LIMIT 8
            """
        )
        print(f"--- {label}: stored_files ---")
        for row in cur.fetchall():
            print(row)
        conn.close()
    except Exception as e:
        print(f"--- {label}: DB error: {e} ---")


def _steps_image(uid: int, ts: int) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "bot_started",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "bot_started",
                "timestamp": ts,
                "user": {"user_id": uid, "is_bot": False, "first_name": "Live"},
            },
        ),
        (
            "mode_consumer",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "message_callback",
                "timestamp": ts + 1,
                "callback": {
                    "callback_id": f"cb-mode-{uuid.uuid4().hex[:10]}",
                    "payload": "v1|mode|consumer",
                    "user": {"user_id": uid, "is_bot": False},
                },
            },
        ),
        (
            "image_btn",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "message_callback",
                "timestamp": ts + 2,
                "callback": {
                    "callback_id": f"cb-img-{uuid.uuid4().hex[:10]}",
                    "payload": "v1|consumer|create_image",
                    "user": {"user_id": uid, "is_bot": False},
                },
            },
        ),
        (
            "image_prompt",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "message_created",
                "timestamp": ts + 3,
                "message": {
                    "sender": {"user_id": uid, "is_bot": False, "first_name": "Live"},
                    "recipient": {},
                    "timestamp": ts + 3,
                    "body": {
                        "mid": f"m-{uuid.uuid4().hex[:14]}",
                        "text": "Закат над морем, тёплые тона, без людей, стиль фото.",
                    },
                },
            },
        ),
    ]


def _steps_greeting(uid: int, ts: int) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "bot_started",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "bot_started",
                "timestamp": ts,
                "user": {"user_id": uid, "is_bot": False, "first_name": "Live"},
            },
        ),
        (
            "mode_consumer",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "message_callback",
                "timestamp": ts + 1,
                "callback": {
                    "callback_id": f"cb-mode-{uuid.uuid4().hex[:10]}",
                    "payload": "v1|mode|consumer",
                    "user": {"user_id": uid, "is_bot": False},
                },
            },
        ),
        (
            "greeting_btn",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "message_callback",
                "timestamp": ts + 2,
                "callback": {
                    "callback_id": f"cb-gr-{uuid.uuid4().hex[:10]}",
                    "payload": "v1|consumer|make_greeting",
                    "user": {"user_id": uid, "is_bot": False},
                },
            },
        ),
        (
            "greeting_text",
            {
                "update_id": str(uuid.uuid4()),
                "update_type": "message_created",
                "timestamp": ts + 3,
                "message": {
                    "sender": {"user_id": uid, "is_bot": False, "first_name": "Live"},
                    "recipient": {},
                    "timestamp": ts + 3,
                    "body": {
                        "mid": f"m-{uuid.uuid4().hex[:14]}",
                        "text": "Поздравление для мамы с днём рождения 65 лет, тёплый тон, без сложных слов.",
                    },
                },
            },
        ),
    ]


def _post_all(base: str, steps: list[tuple[str, dict[str, Any]]]) -> int:
    with httpx.Client(timeout=120.0) as client:
        for name, body in steps:
            r = client.post(f"{base}/webhooks/max", json=body)
            print(name, r.status_code, r.text[:100])
            if r.status_code >= 400:
                return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument(
        "--uid",
        type=int,
        default=900_001,
        help="max_user_id в MAX (для live укажите свой реальный id)",
    )
    p.add_argument("--flow", choices=("image", "greeting", "both"), default="image")
    p.add_argument("--wait-image", type=int, default=120, help="сек ожидания после image flow")
    p.add_argument("--wait-greeting", type=int, default=180, help="сек ожидания после greeting (текст+картинка)")
    args = p.parse_args()
    base = args.base.rstrip("/")
    uid = args.uid
    ts = int(time.time())

    if args.flow == "image":
        steps = _steps_image(uid, ts)
        if _post_all(base, steps) != 0:
            return 1
        print(f"--- ждём {args.wait_image}s (Yandex Art + MAX outbound) ---")
        time.sleep(args.wait_image)
        _poll_db("after_image")
        return 0

    if args.flow == "greeting":
        steps = _steps_greeting(uid, ts)
        if _post_all(base, steps) != 0:
            return 1
        print(f"--- ждём {args.wait_greeting}s (текст Yandex + картинка + MAX) ---")
        time.sleep(args.wait_greeting)
        _poll_db("after_greeting")
        return 0

    # both: один пользователь — сначала картинка, затем поздравление (без второго bot_started)
    steps_i = _steps_image(uid, ts)
    if _post_all(base, steps_i) != 0:
        return 1
    print(f"--- ждём {args.wait_image}s после image ---")
    time.sleep(args.wait_image)
    _poll_db("after_image")

    ts2 = int(time.time())
    steps_g = _steps_greeting(uid, ts2)[2:]  # только greeting_btn + greeting_text
    if _post_all(base, steps_g) != 0:
        return 1
    print(f"--- ждём {args.wait_greeting}s после greeting ---")
    time.sleep(args.wait_greeting)
    _poll_db("after_greeting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
