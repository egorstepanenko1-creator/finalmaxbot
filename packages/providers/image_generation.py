"""Генерация изображений: stub (Pillow) и опционально Yandex Art async."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from typing import Any, Protocol, runtime_checkable

import httpx
from PIL import Image, ImageDraw

from packages.domain.image_generation import ImageGenerationResult
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)

# Лимит тела ответа Yandex в логах / safe_meta (без секретов)
_MAX_ERROR_BODY_LOG = 16_384


def _safe_yandex_submit_log_fields(body: dict[str, Any]) -> dict[str, Any]:
    """Поля запроса imageGenerationAsync, безопасные для логов (без ключей)."""
    msgs = body.get("messages")
    n = len(msgs) if isinstance(msgs, list) else 0
    first_text = ""
    first_weight: Any = None
    if n and isinstance(msgs[0], dict):
        first_weight = msgs[0].get("weight")
        first_text = str(msgs[0].get("text", ""))[:200]
    return {
        "modelUri": body.get("modelUri"),
        "generationOptions": body.get("generationOptions"),
        "messages_count": n,
        "first_message_weight": first_weight,
        "first_message_text_prefix": first_text,
    }


@runtime_checkable
class ImageGenerationPort(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        correlation_id: str,
        meta: dict[str, Any] | None,
    ) -> ImageGenerationResult: ...


def _find_base64_image(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("bytesBase64", "bytes_base64", "image", "data", "content") and isinstance(v, str):
                if len(v) > 80:
                    return v
            got = _find_base64_image(v)
            if got:
                return got
    elif isinstance(obj, list):
        for x in obj:
            got = _find_base64_image(x)
            if got:
                return got
    return None


def _stub_sync_generate(prompt: str, correlation_id: str) -> ImageGenerationResult:
    w, h = 768, 768
    img = Image.new("RGB", (w, h), (35, 55, 90))
    draw = ImageDraw.Draw(img)
    for i in range(0, w + h, 36):
        draw.line([(i, 0), (0, i)], fill=(210, 175, 120), width=1)
    label = f"stub\n{correlation_id[:10]}\n" + prompt.strip().replace("\n", " ")[:80]
    draw.text((32, 32), label, fill=(255, 255, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return ImageGenerationResult(
        ok=True,
        image_bytes=buf.getvalue(),
        mime_type="image/png",
        provider="stub_pillow",
        safe_meta={"width": w, "height": h},
    )


class StubPillowImageProvider:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def generate(
        self,
        *,
        prompt: str,
        correlation_id: str,
        meta: dict[str, Any] | None = None,
    ) -> ImageGenerationResult:
        _ = (self._s, meta)
        return await asyncio.to_thread(_stub_sync_generate, prompt, correlation_id)


class YandexFoundationImageProvider:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _model_uri(self) -> str:
        if self._s.yandex_image_model_uri:
            return self._s.yandex_image_model_uri
        fid = self._s.yandex_folder_id or ""
        return f"art://{fid}/yandex-art/latest"

    def _safe_op_meta(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(data, ensure_ascii=False)[:4000]
        try:
            return json.loads(raw) if raw.startswith("{") else {"truncated": raw}
        except json.JSONDecodeError:
            return {"truncated": raw[:2000]}

    async def generate(
        self,
        *,
        prompt: str,
        correlation_id: str,
        meta: dict[str, Any] | None = None,
    ) -> ImageGenerationResult:
        _ = meta
        key = self._s.yandex_cloud_api_key
        folder = self._s.yandex_folder_id
        if not key or not folder:
            return await StubPillowImageProvider(self._s).generate(
                prompt=prompt, correlation_id=correlation_id, meta=meta
            )
        headers = {
            "Authorization": f"Api-Key {key}",
            "x-folder-id": folder,
            "Content-Type": "application/json",
        }
        model_uri = self._model_uri()
        # Формат REST Yandex Art: messages[].text + weight (строка), см. официальные примеры / Habr.
        body: dict[str, Any] = {
            "modelUri": model_uri,
            "generationOptions": {"aspectRatio": {"widthRatio": "1", "heightRatio": "1"}},
            "messages": [
                {
                    "weight": "1",
                    "text": prompt[:2000],
                }
            ],
        }
        job_id = (meta or {}).get("job_id")
        req_safe = _safe_yandex_submit_log_fields(body)
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(self._s.yandex_image_async_url, headers=headers, json=body)
            if r.status_code >= 400:
                err_body = (r.text or "")[:_MAX_ERROR_BODY_LOG]
                logger.error(
                    "m5_event=image_provider_submit_failed correlation_id=%s job_id=%s "
                    "http_status=%s model_uri=%s endpoint=%s request_safe=%s",
                    correlation_id,
                    job_id,
                    r.status_code,
                    model_uri,
                    self._s.yandex_image_async_url,
                    json.dumps(req_safe, ensure_ascii=False),
                )
                logger.error(
                    "m5_event=image_provider_submit_failed_body correlation_id=%s response_body=%s",
                    correlation_id,
                    err_body,
                )
                return ImageGenerationResult(
                    ok=False,
                    image_bytes=None,
                    mime_type="image/png",
                    provider="yandex_art",
                    error_code=f"http_{r.status_code}",
                    safe_meta={
                        "submit": r.status_code,
                        "model_uri": model_uri,
                        "endpoint": self._s.yandex_image_async_url,
                        "correlation_id": correlation_id,
                        "job_id": job_id,
                        "request_safe": req_safe,
                        "response_body": err_body,
                    },
                )
            op = r.json()
            op_id = op.get("id")
            if not op_id:
                return ImageGenerationResult(
                    ok=False,
                    image_bytes=None,
                    mime_type="image/png",
                    provider="yandex_art",
                    error_code="no_operation_id",
                    safe_meta=self._safe_op_meta(op),
                )
            deadline = time.monotonic() + self._s.yandex_image_poll_timeout_sec
            last: dict[str, Any] = {}
            while time.monotonic() < deadline:
                await asyncio.sleep(self._s.yandex_image_poll_interval_sec)
                poll_url = self._s.yandex_image_operations_url_template.format(operation_id=op_id)
                async with httpx.AsyncClient(timeout=60.0) as client:
                    pr = await client.get(poll_url, headers=headers)
                if pr.status_code >= 400:
                    logger.warning(
                        "m5_event=image_provider_poll_http correlation_id=%s status=%s",
                        correlation_id,
                        pr.status_code,
                    )
                    continue
                last = pr.json()
                if last.get("done"):
                    break
            elapsed = time.monotonic() - t0
            if not last.get("done"):
                return ImageGenerationResult(
                    ok=False,
                    image_bytes=None,
                    mime_type="image/png",
                    provider="yandex_art",
                    error_code="poll_timeout",
                    safe_meta={"operation_id": op_id, "elapsed_sec": round(elapsed, 2)},
                )
            if last.get("error"):
                return ImageGenerationResult(
                    ok=False,
                    image_bytes=None,
                    mime_type="image/png",
                    provider="yandex_art",
                    error_code="operation_error",
                    safe_meta={"operation_id": op_id, "error": str(last.get("error"))[:500]},
                )
            b64 = _find_base64_image(last.get("response") or last)
            if not b64:
                return ImageGenerationResult(
                    ok=False,
                    image_bytes=None,
                    mime_type="image/png",
                    provider="yandex_art",
                    error_code="no_image_in_response",
                    safe_meta={"operation_id": op_id, "keys": list(last.keys())},
                )
            raw_b = base64.b64decode(b64)
            logger.info(
                "m5_event=image_provider_finished correlation_id=%s provider=yandex_art bytes=%s elapsed_sec=%.2f",
                correlation_id,
                len(raw_b),
                elapsed,
            )
            return ImageGenerationResult(
                ok=True,
                image_bytes=raw_b,
                mime_type="image/jpeg",
                provider="yandex_art",
                safe_meta={"operation_id": op_id, "elapsed_sec": round(elapsed, 2)},
            )
        except Exception as e:
            logger.exception("m5_event=image_provider_exception correlation_id=%s", correlation_id)
            return ImageGenerationResult(
                ok=False,
                image_bytes=None,
                mime_type="image/png",
                provider="yandex_art",
                error_code=type(e).__name__,
                safe_meta={},
            )


def build_image_generation(settings: Settings) -> ImageGenerationPort:
    if (
        settings.yandex_image_generation_enabled
        and settings.yandex_cloud_api_key
        and settings.yandex_folder_id
    ):
        return YandexFoundationImageProvider(settings)
    return StubPillowImageProvider(settings)
