"""Локальное хранилище файлов для разработки."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any


class LocalFileStorage:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    async def save_bytes(
        self,
        *,
        data: bytes,
        mime_type: str,
        meta_hint: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        _ = meta_hint
        h = hashlib.sha256(data).hexdigest()
        uid = uuid.uuid4().hex
        ext = ".png" if "png" in mime_type else ".jpg" if "jpeg" in mime_type or mime_type == "image/jpg" else ".bin"
        rel = f"{h[:2]}/{uid}{ext}"
        path = self._root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return "local", rel

    async def read_bytes(self, *, storage_backend: str, storage_key: str) -> bytes:
        if storage_backend != "local":
            raise ValueError(f"unsupported backend {storage_backend}")
        p = self._root / storage_key
        return p.read_bytes()
