from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from packages.db import models  # noqa: F401, E402
from packages.db.base import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_raw_database_url() -> str | None:
    """Приоритет: os.environ (в т.ч. из .env через load_dotenv), затем sqlalchemy.url в alembic.ini."""
    env_url = os.environ.get("DATABASE_URL")
    if env_url is not None and str(env_url).strip():
        return str(env_url).strip()
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url and str(ini_url).strip():
        s = str(ini_url).strip()
        if s.startswith("%("):
            return None
        return s
    return None


def _sync_url() -> str:
    raw = _get_raw_database_url()
    if raw is None:
        raw = "sqlite+aiosqlite:///./finalmaxbot.db"

    if raw.startswith("sqlite+aiosqlite"):
        return raw.replace("sqlite+aiosqlite:", "sqlite:", 1)

    url = raw
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)

    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("ssl=require", "sslmode=require")

    return url


def run_migrations_offline() -> None:
    url = _sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_sync_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
