from __future__ import annotations

import logging
from typing import Any

from apps.bot.interaction_router import InteractionRouter
from apps.bot.max_client import MaxBotClient
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


async def handle_max_update(
    update: dict[str, Any],
    *,
    session: Any,
    session_factory: Any,
    client: MaxBotClient,
    settings: Settings,
    after_commit: list[Any] | None = None,
) -> None:
    bucket = after_commit if after_commit is not None else []
    router = InteractionRouter(settings, session_factory, bucket)
    await router.route(update, session, client)
