"""
Проверка: MAX Bot API (GET /me), Supabase REST (опционально), Postgres (DATABASE_URL).

Запуск из корня репозитория: python scripts/verify_setup.py

Если Postgres даёт getaddrinfo failed на db.<ref>.supabase.co — у проекта часто только IPv6.
Возьмите в Dashboard → Database строку «Session pooler» / «IPv4» и вставьте в DATABASE_URL.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _db_host_ipv4_hint(hostname: str) -> None:
    """Проверка A/AAAA для db.<ref>.supabase.co — подсказка про IPv4 pooler."""
    if not hostname.endswith(".supabase.co"):
        return
    try:
        socket.getaddrinfo(hostname, 5432, type=socket.SOCK_STREAM)
        return
    except OSError:
        pass
    try:
        r = httpx.get(
            "https://cloudflare-dns.com/dns-query",
            params={"name": hostname, "type": "A"},
            headers={"accept": "application/dns-json"},
            timeout=10,
        )
        data = r.json()
        has_a = bool(data.get("Answer"))
    except Exception:
        has_a = False
    try:
        r = httpx.get(
            "https://cloudflare-dns.com/dns-query",
            params={"name": hostname, "type": "AAAA"},
            headers={"accept": "application/dns-json"},
            timeout=10,
        )
        data = r.json()
        has_aaaa = bool(data.get("Answer"))
    except Exception:
        has_aaaa = False
    if not has_a and has_aaaa:
        print(
            "Подсказка: для этого хоста в DNS есть только IPv6 (AAAA). "
            "На Windows без IPv6 используйте строку Session pooler (IPv4) из "
            "Supabase Dashboard (раздел Database)."
        )


async def main() -> int:
    from packages.db.session import create_engine
    from packages.shared.settings import get_settings, normalize_async_database_url

    get_settings.cache_clear()

    if not (ROOT / ".env").exists():
        print("Нет файла .env в корне проекта. Скопируйте .env.example → .env и заполните.")
        return 2

    s = get_settings()

    if s.supabase_url and s.supabase_anon_key:
        try:
            u = s.supabase_url.rstrip("/") + "/auth/v1/health"
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    u,
                    headers={
                        "apikey": s.supabase_anon_key,
                        "Authorization": f"Bearer {s.supabase_anon_key}",
                    },
                )
            if r.status_code < 500:
                print("Supabase REST (auth health): OK", r.status_code)
            else:
                print("Supabase REST: странный ответ", r.status_code, r.text[:200])
        except Exception as e:
            print("Supabase REST: FAIL", type(e).__name__, e)

    if not s.max_bot_token:
        print("MAX_BOT_TOKEN пуст — проверка platform-api пропущена.")
    else:
        url = f"{s.max_api_base.rstrip('/')}/me"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers={"Authorization": s.max_bot_token})
        if r.status_code != 200:
            print("MAX GET /me: FAIL", r.status_code, r.text[:300])
            return 1
        print("MAX GET /me: OK")

    url_norm = normalize_async_database_url(s.database_url)
    if url_norm.startswith("sqlite"):
        print("DATABASE_URL: sqlite — проверка SELECT 1...")
    else:
        print("DATABASE_URL: postgres — проверка SELECT 1...")
        parsed = urlparse(s.database_url.replace("postgresql+asyncpg://", "postgresql://"))
        if parsed.hostname:
            _db_host_ipv4_hint(parsed.hostname)

    engine = create_engine(s.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        print("Postgres: OK (SELECT 1)")
    except OSError as e:
        print("Postgres: FAIL (сеть/DNS)", type(e).__name__, e)
        return 1
    except Exception as e:
        print("Postgres: FAIL", type(e).__name__, e)
        return 1
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
