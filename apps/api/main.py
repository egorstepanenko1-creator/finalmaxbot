import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from fastapi import FastAPI

from alembic import command
from apps.api.billing_webhook import router as billing_webhook_router
from apps.api.internal_launch import router as internal_launch_router
from apps.api.internal_m4 import router as internal_m4_router
from apps.api.internal_m7 import router as internal_m7_router
from apps.bot.router import router as max_router
from packages.db.session import create_engine, get_session_factory, init_db
from packages.shared.settings import get_settings
from packages.shared.startup_checks import warn_launch_readiness

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    warn_launch_readiness(settings)
    os.environ["DATABASE_URL"] = settings.database_url
    root = Path(__file__).resolve().parents[2]
    if settings.run_alembic_on_startup:
        cfg = Config(str(root / "alembic.ini"))
        command.upgrade(cfg, "head")
        logger.info("Alembic upgrade head ok")
    engine = create_engine(settings.database_url)
    if settings.allow_runtime_create_all:
        await init_db(engine)
        logger.info("Runtime create_all applied (local flag)")
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
    app.include_router(internal_m4_router)
    app.include_router(internal_m7_router)
    app.include_router(internal_launch_router)
    app.include_router(billing_webhook_router)
    return app


app = create_app()
