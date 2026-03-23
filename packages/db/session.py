from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from packages.db.base import Base
from packages.shared.settings import normalize_async_database_url


def create_engine(database_url: str) -> AsyncEngine:
    url = normalize_async_database_url(database_url)
    # Supabase / serverless: избегаем долгих соединений в пуле при простых деплоях
    if url.startswith("postgresql"):
        engine = create_async_engine(
            url,
            poolclass=NullPool,
        )
    else:
        engine = create_async_engine(url)

    if "sqlite" in url:
        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_fk(dbapi_connection: object, _connection_record: object) -> None:
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    import packages.db.models  # noqa: F401 — регистрация таблиц в Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
