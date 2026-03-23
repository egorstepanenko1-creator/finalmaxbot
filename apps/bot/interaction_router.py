"""Тонкий маршрутизатор: тип MAX update → state machine."""

from __future__ import annotations

from typing import Any

from apps.bot.generation_factory import build_generation_orchestrator
from apps.bot.max_client import MaxBotClient
from apps.bot.max_payload import extract_update_type
from apps.bot.state_machine_service import StateMachineService
from packages.billing.stub_service import StubBillingCheckoutService
from packages.providers.text_generation import build_text_generation
from packages.shared.settings import Settings


class InteractionRouter:
    def __init__(
        self,
        settings: Settings,
        session_factory: Any,
        after_commit: list[Any] | None = None,
    ) -> None:
        self._settings = settings
        self._after_commit = after_commit if after_commit is not None else []
        text = build_text_generation(settings)
        orch = build_generation_orchestrator(settings, session_factory, text)
        self._sm = StateMachineService(
            text,
            StubBillingCheckoutService(),
            settings,
            orchestrator=orch,
            after_commit=self._after_commit,
        )

    async def route(self, update: dict[str, Any], session: Any, client: MaxBotClient) -> None:
        ut = extract_update_type(update)
        if ut == "bot_started":
            await self._sm.on_bot_started(update, session, client)
        elif ut == "message_created":
            await self._sm.on_message_created(update, session, client)
        elif ut == "message_callback":
            await self._sm.on_callback(update, session, client)
        else:
            pass
