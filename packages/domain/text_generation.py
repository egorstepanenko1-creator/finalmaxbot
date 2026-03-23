"""Стабильная модель ответа текстовой генерации (M5)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextGenerationOutput:
    """Текст для пользователя + признак успеха (для квот и метрик)."""

    text: str
    ok: bool
    provider: str
    error_code: str | None = None
