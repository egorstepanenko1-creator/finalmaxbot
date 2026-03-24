import asyncio
import json
import logging
from typing import Any

import httpx

from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


class MaxBotClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.max_api_base.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.max_bot_token and self._settings.max_outbound_enabled
        )

    def _headers(self) -> dict[str, str]:
        token = self._settings.max_bot_token or ""
        return {"Authorization": token, "Content-Type": "application/json"}

    async def send_message(
        self,
        *,
        user_id: int,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        fmt: str | None = None,
    ) -> bool:
        if not self.enabled:
            logger.info(
                "MAX outbound skipped (no token or disabled): user_id=%s text=%r",
                user_id,
                text[:200],
            )
            return True
        body: dict[str, Any] = {"text": text}
        if attachments:
            body["attachments"] = attachments
        if fmt:
            body["format"] = fmt
        url = f"{self._base}/messages"
        log_body: dict[str, Any] = dict(body)
        if attachments:
            log_body["attachments"] = [
                {
                    "type": a.get("type"),
                    "payload": (
                        {"token_set": bool((a.get("payload") or {}).get("token"))}
                        if isinstance(a.get("payload"), dict)
                        else a.get("payload")
                    ),
                }
                for a in attachments
            ]
        logger.info(
            "m5_event=max_outbound_messages_request user_id=%s body=%s",
            user_id,
            json.dumps(log_body, ensure_ascii=False)[:4000],
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                url,
                params={"user_id": user_id},
                headers=self._headers(),
                json=body,
            )
            if r.status_code >= 400:
                logger.warning(
                    "MAX POST /messages failed: %s %s %s",
                    r.status_code,
                    r.text[:500],
                    user_id,
                )
                return False
            logger.info(
                "m5_event=max_outbound_messages_ok user_id=%s status=%s attachment_count=%s",
                user_id,
                r.status_code,
                len(attachments or []),
            )
            return True

    async def upload_image_bytes(
        self,
        data: bytes,
        *,
        filename: str = "image.png",
        content_type: str = "image/png",
    ) -> str | None:
        """POST /uploads?type=image, затем multipart на выданный url. Возвращает token."""
        if not self.enabled:
            logger.info("MAX upload skipped (disabled)")
            return None
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{self._base}/uploads",
                params={"type": "image"},
                headers=self._headers(),
            )
            if r.status_code >= 400:
                logger.warning("MAX POST /uploads failed: %s %s", r.status_code, r.text[:400])
                return None
            try:
                payload = r.json()
            except json.JSONDecodeError:
                logger.warning("MAX /uploads invalid json")
                return None
            upload_url = payload.get("url")
            if not upload_url:
                logger.warning("MAX /uploads no url in %s", payload)
                return None
            files = {"data": (filename, data, content_type)}
            ru = await client.post(upload_url, headers=self._headers(), files=files)
            if ru.status_code >= 400:
                logger.warning("MAX upload PUT failed: %s %s", ru.status_code, ru.text[:400])
                return None
            try:
                up = ru.json()
            except json.JSONDecodeError:
                up = {}
            token = up.get("token")
            if not token:
                logger.warning("MAX upload response without token: %s", str(up)[:300])
                return None
            return str(token)

    async def send_message_with_image(
        self,
        *,
        user_id: int,
        text: str,
        image_bytes: bytes,
        image_mime: str = "image/png",
        fmt: str | None = None,
    ) -> bool:
        filename = "image.png" if "png" in image_mime else "image.jpg"
        ct = image_mime if "/" in image_mime else "image/png"
        token = await self.upload_image_bytes(data=image_bytes, filename=filename, content_type=ct)
        if not token:
            return False
        delay = self._settings.m5_max_upload_ready_delay_sec
        if delay > 0:
            await asyncio.sleep(delay)
        att = [{"type": "image", "payload": {"token": token}}]
        retries = max(1, self._settings.m5_max_send_attachment_retries)
        for attempt in range(retries):
            ok = await self.send_message(user_id=user_id, text=text, attachments=att, fmt=fmt)
            if ok:
                return True
            await asyncio.sleep(0.75 * (attempt + 1))
        logger.warning("m5_event=max_image_send_exhausted user_id=%s", user_id)
        return False

    async def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            logger.info(
                "MAX answer_callback skipped: callback_id=%s notification=%r",
                callback_id,
                notification,
            )
            return
        url = f"{self._base}/answers"
        body: dict[str, Any] = {}
        if notification is not None:
            body["notification"] = notification
        if message is not None:
            body["message"] = message
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                url,
                params={"callback_id": callback_id},
                headers=self._headers(),
                json=body,
            )
            if r.status_code >= 400:
                logger.warning(
                    "MAX POST /answers failed: %s %s",
                    r.status_code,
                    r.text[:500],
                )
