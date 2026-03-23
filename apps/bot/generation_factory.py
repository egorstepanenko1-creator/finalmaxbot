from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.bot.generation_orchestrator import GenerationOrchestrator
from packages.providers.image_generation import build_image_generation
from packages.providers.text_generation import TextGenerationPort
from packages.shared.settings import Settings
from packages.storage.local import LocalFileStorage


def build_generation_orchestrator(
    settings: Settings,
    session_factory: Any,
    text_port: TextGenerationPort,
) -> GenerationOrchestrator:
    Path(settings.m5_local_storage_root).mkdir(parents=True, exist_ok=True)
    return GenerationOrchestrator(
        settings=settings,
        session_factory=session_factory,
        text_port=text_port,
        image_port=build_image_generation(settings),
        storage=LocalFileStorage(settings.m5_local_storage_root),
    )
