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
    ) -> None:
        if not self.enabled:
            logger.info(
                "MAX outbound skipped (no token or disabled): user_id=%s text=%r",
                user_id,
                text[:200],
            )
            return
        body: dict[str, Any] = {"text": text}
        if attachments:
            body["attachments"] = attachments
        if fmt:
            body["format"] = fmt
        url = f"{self._base}/messages"
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
            else:
                logger.debug("MAX POST /messages ok user_id=%s", user_id)

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
