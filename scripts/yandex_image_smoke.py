#!/usr/bin/env python3
"""Смоук Yandex Art: submit + poll без MAX (только провайдер). Загружает .env из корня репозитория.

Пример:
  python scripts/yandex_image_smoke.py закат над морем, тёплые тона
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from packages.providers.image_generation import YandexFoundationImageProvider
    from packages.shared.settings import get_settings

    return asyncio.run(_amain(get_settings, YandexFoundationImageProvider))


async def _amain(get_settings_fn, provider_cls) -> int:
    get_settings_fn.cache_clear()
    settings = get_settings_fn()
    prompt = " ".join(sys.argv[1:]).strip() or "Минималистичный оранжевый круг на белом фоне"
    prov = provider_cls(settings)
    correlation_id = "cli-yandex-image-smoke"
    meta = {"job_id": None}
    res = await prov.generate(prompt=prompt, correlation_id=correlation_id, meta=meta)
    note = (
        "При ok=True байты готовы для цепочки upload + POST /messages "
        "(см. MaxBotClient.send_message_with_image)."
    )
    payload = {
        "ok": res.ok,
        "provider": res.provider,
        "error_code": res.error_code,
        "mime_type": res.mime_type,
        "image_bytes_len": len(res.image_bytes or b""),
        "safe_meta": res.safe_meta,
        "max_outbound_note": note,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if res.ok else 1


def main() -> None:
    raise SystemExit(_run())


if __name__ == "__main__":
    main()
