import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.bot.router import router as max_router
from packages.db.session import create_engine, get_session_factory, init_db
from packages.shared.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    await init_db(engine)
    factory = get_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = factory
    logger.info("DB ready url=%s", _safe_db_url(settings.database_url))
    yield
    await engine.dispose()


def _safe_db_url(url: str) -> str:
    if "@" in url:
        return url.split("@")[-1]
    return url


def create_app() -> FastAPI:
    app = FastAPI(title="finalmaxbot", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(max_router)
    return app


app = create_app()
