"""Результат генерации изображения у провайдера (M5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImageGenerationResult:
    ok: bool
    image_bytes: bytes | None
    mime_type: str
    provider: str
    error_code: str | None = None
    safe_meta: dict[str, Any] = field(default_factory=dict)
