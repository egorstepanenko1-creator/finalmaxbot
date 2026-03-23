"""Token для T-Bank / Tinkoff Acquiring API v2 (без секретов в логах).

Алгоритм: значения всех полей запроса (кроме Token), отсортированные по имени ключа,
в порядке возрастания ключей, конкатенируются; в конец добавляется Password.
SHA-256 от строки в UTF-8, hex.

См. документацию эквайринга T-Bank (раздел подпись запроса).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _serialize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def build_tbank_token(params: dict[str, Any], *, password: str) -> str:
    """params — плоский словарь; поле Token не участвует."""
    parts: list[tuple[str, str]] = []
    for key, raw in params.items():
        if key == "Token":
            continue
        if raw is None:
            continue
        parts.append((key, _serialize_value(raw)))
    parts.sort(key=lambda x: x[0])
    concat = "".join(v for _k, v in parts) + password
    return hashlib.sha256(concat.encode("utf-8")).hexdigest()


def attach_token(params: dict[str, Any], *, password: str) -> dict[str, Any]:
    out = {k: v for k, v in params.items() if k != "Token"}
    out["Token"] = build_tbank_token(out, password=password)
    return out
