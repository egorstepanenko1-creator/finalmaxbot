"""Проверка ping_database (реальный round-trip к SQLite in-memory)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from packages.db.session import ping_database


@pytest.mark.asyncio
async def test_ping_database_sqlite_memory() -> None:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        await ping_database(eng)
    finally:
        await eng.dispose()
