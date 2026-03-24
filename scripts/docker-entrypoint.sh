#!/bin/sh
set -e
# Ожидание TCP к Postgres, если URL указывает на postgres (Supabase / docker-compose.postgres.yml).
case "${DATABASE_URL:-}" in
  *postgres*)
    python - <<'PY'
import os
import socket
import time
from urllib.parse import urlparse

raw = os.environ.get("DATABASE_URL", "")
u = urlparse(raw.replace("postgresql+asyncpg://", "http://", 1))
host = u.hostname
port = u.port or 5432
if not host:
    raise SystemExit("DATABASE_URL: не удалось определить хост БД")
deadline = time.monotonic() + float(os.environ.get("DB_WAIT_TIMEOUT_SEC", "90"))
while time.monotonic() < deadline:
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"БД недоступна: {host}:{port}")
PY
    ;;
esac

exec "$@"
