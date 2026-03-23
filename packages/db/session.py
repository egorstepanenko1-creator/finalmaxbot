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
        return create_async_engine(
            url,
            poolclass=NullPool,
        )
    return create_async_engine(url)


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
