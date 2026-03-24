import asyncio
import json
import logging
from typing import Any

import httpx

from apps.bot.outbound_context import outbound_max_chat_id
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


def _max_error_code(r: httpx.Response) -> str | None:
    try:
        j = r.json()
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(j, dict):
        return None
    c = j.get("code")
    if c is not None:
        return str(c)
    err = j.get("error")
    if isinstance(err, dict) and err.get("code") is not None:
        return str(err.get("code"))
    return None


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

    def _effective_chat_id(self, chat_id: int | None) -> int | None:
        if chat_id is not None:
            return chat_id
        return outbound_max_chat_id.get()

    async def _post_messages(
        self,
        *,
        user_id: int,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        fmt: str | None = None,
        chat_id: int | None = None,
    ) -> tuple[bool, str | None]:
        """
        POST /messages с ?chat_id= (предпочтительно, как max-bot-mvp) или ?user_id=.
        Возвращает (ok, error_code) для ретраев attachment.not.ready.
        """
        if not self.enabled:
            logger.info(
                "MAX outbound skipped (no token or disabled): user_id=%s text=%r",
                user_id,
                text[:200],
            )
            return True, None
        eff_chat = self._effective_chat_id(chat_id)
        params: dict[str, str] = (
            {"chat_id": str(eff_chat)}
            if eff_chat is not None
            else {"user_id": str(user_id)}
        )
        body: dict[str, Any] = {"text": text}
        if attachments:
            body["attachments"] = attachments
        if fmt:
            body["format"] = fmt
        url = f"{self._base}/messages"
        log_body: dict[str, Any] = dict(body)
        if attachments:
            log_attachments: list[dict[str, Any]] = []
            for a in attachments:
                pl = a.get("payload")
                if isinstance(pl, dict):
                    log_attachments.append(
                        {
                            "type": a.get("type"),
                            "payload": {
                                k: ("***" if k == "token" else v)
                                for k, v in pl.items()
                            },
                        }
                    )
                else:
                    log_attachments.append({"type": a.get("type"), "payload": pl})
            log_body["attachments"] = log_attachments
        logger.info(
            "m5_event=max_outbound_messages_request user_id=%s chat_id=%s query=%s body=%s",
            user_id,
            eff_chat,
            params,
            json.dumps(log_body, ensure_ascii=False)[:4000],
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                url,
                params=params,
                headers=self._headers(),
                json=body,
            )
            if r.status_code >= 400:
                code = _max_error_code(r)
                logger.warning(
                    "MAX POST /messages failed: %s %s %s",
                    r.status_code,
                    r.text[:500],
                    user_id,
                )
                return False, code
            logger.info(
                "m5_event=max_outbound_messages_ok user_id=%s chat_id=%s status=%s attachment_count=%s",
                user_id,
                eff_chat,
                r.status_code,
                len(attachments or []),
            )
            return True, None

    async def send_message(
        self,
        *,
        user_id: int,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        fmt: str | None = None,
        chat_id: int | None = None,
    ) -> bool:
        ok, _ = await self._post_messages(
            user_id=user_id,
            text=text,
            attachments=attachments,
            fmt=fmt,
            chat_id=chat_id,
        )
        return ok

    async def upload_image_payload(
        self,
        data: bytes,
        *,
        filename: str = "image.png",
        content_type: str = "image/png",
    ) -> dict[str, Any] | None:
        """
        POST /uploads?type=image, затем POST на выданный url.
        Второй запрос — без Authorization (как max-bot-mvp: только подписанный URL).
        Возвращает полный JSON ответа второго шага для attachment.payload.
        """
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
            # Важно: не передаём bot token на внешний upload URL — иначе BAD_REQUEST у uploadImage.
            ru = await client.post(str(upload_url), files=files)
            if ru.status_code >= 400:
                logger.warning("MAX upload stage2 failed: %s %s", ru.status_code, ru.text[:400])
                return None
            try:
                up = ru.json()
            except json.JSONDecodeError:
                up = {}
            if not isinstance(up, dict):
                logger.warning("MAX upload stage2 not a dict: %s", str(up)[:300])
                return None
            if not up.get("token") and up.get("photo_id") is None:
                logger.warning("MAX upload response without token/photo_id: %s", str(up)[:300])
                return None
            return up

    async def send_message_with_image(
        self,
        *,
        user_id: int,
        text: str,
        image_bytes: bytes,
        image_mime: str = "image/png",
        fmt: str | None = None,
        chat_id: int | None = None,
    ) -> bool:
        filename = "image.png" if "png" in image_mime else "image.jpg"
        ct = image_mime if "/" in image_mime else "image/png"
        image_payload = await self.upload_image_payload(
            data=image_bytes, filename=filename, content_type=ct
        )
        if not image_payload:
            return False
        delay = self._settings.m5_max_upload_ready_delay_sec
        if delay > 0:
            await asyncio.sleep(delay)
        att = [{"type": "image", "payload": dict(image_payload)}]
        max_attempts = max(4, max(1, self._settings.m5_max_send_attachment_retries))
        for attempt in range(1, max_attempts + 1):
            ok, err_code = await self._post_messages(
                user_id=user_id,
                text=text,
                attachments=att,
                fmt=fmt,
                chat_id=chat_id,
            )
            if ok:
                return True
            if err_code == "attachment.not.ready" and attempt < max_attempts:
                wait_ms = int(1200 * attempt)
                logger.warning(
                    "m5_event=max_attachment_not_ready_retry attempt=%s wait_ms=%s",
                    attempt,
                    wait_ms,
                )
                await asyncio.sleep(wait_ms / 1000.0)
                continue
            await asyncio.sleep(0.75 * attempt)
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
