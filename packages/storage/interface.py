"""Абстракция хранения бинарных артефактов (локально, позже S3)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class FileStoragePort(Protocol):
    async def save_bytes(
        self,
        *,
        data: bytes,
        mime_type: str,
        meta_hint: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Вернуть (storage_backend, storage_key)."""

    async def read_bytes(self, *, storage_backend: str, storage_key: str) -> bytes: ...
