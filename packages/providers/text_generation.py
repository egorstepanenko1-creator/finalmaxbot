from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from packages.domain.text_generation import TextGenerationOutput
from packages.shared.settings import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class TextGenerationPort(Protocol):
    async def generate(self, *, system_prompt: str, user_prompt: str) -> TextGenerationOutput: ...


class StubTextGenerationProvider:
    """Детерминированный stub с тем же контрактом, что и облачный провайдер."""

    async def generate(self, *, system_prompt: str, user_prompt: str) -> TextGenerationOutput:
        u = user_prompt.strip().replace("\n", " ")[:400]
        return TextGenerationOutput(
            text=(
                "[stub-текст] Ваш запрос принят.\n\n"
                f"Кратко: {u}\n\n"
                "(Подключите YANDEX_CLOUD_API_KEY и YANDEX_FOLDER_ID для живой генерации.)"
            ),
            ok=True,
            provider="stub",
        )


class YandexFoundationTextProvider:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        fid = settings.yandex_folder_id or ""
        self._model_uri = settings.yandex_model_uri or f"gpt://{fid}/yandexgpt/latest"

    async def generate(self, *, system_prompt: str, user_prompt: str) -> TextGenerationOutput:
        key = self._s.yandex_cloud_api_key
        if not key or not self._s.yandex_folder_id:
            return await StubTextGenerationProvider().generate(
                system_prompt=system_prompt, user_prompt=user_prompt
            )
        body: dict[str, Any] = {
            "modelUri": self._model_uri,
            "completionOptions": {"temperature": 0.25, "maxTokens": 1024},
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Api-Key {key}",
            "x-folder-id": self._s.yandex_folder_id,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    self._s.yandex_completion_url,
                    headers=headers,
                    json=body,
                )
            if r.status_code >= 400:
                logger.warning("Yandex completion HTTP %s: %s", r.status_code, r.text[:500])
                return TextGenerationOutput(
                    text="Не удалось получить ответ от нейросети. Попробуйте позже.",
                    ok=False,
                    provider="yandex",
                    error_code=f"http_{r.status_code}",
                )
            data = r.json()
            alts = data.get("result", {}).get("alternatives") or []
            if not alts:
                return TextGenerationOutput(
                    text="Пустой ответ модели. Переформулируйте, пожалуйста.",
                    ok=False,
                    provider="yandex",
                    error_code="empty_alternatives",
                )
            text = (alts[0].get("message") or {}).get("text")
            t = str(text).strip() if text else ""
            if not t:
                return TextGenerationOutput(
                    text="Пустой ответ модели. Переформулируйте, пожалуйста.",
                    ok=False,
                    provider="yandex",
                    error_code="empty_text",
                )
            return TextGenerationOutput(text=t, ok=True, provider="yandex")
        except Exception as e:
            logger.exception("Yandex completion failed")
            return TextGenerationOutput(
                text="Сервис временно недоступен. Попробуйте чуть позже.",
                ok=False,
                provider="yandex",
                error_code=type(e).__name__,
            )


def build_text_generation(settings: Settings) -> TextGenerationPort:
    if settings.yandex_cloud_api_key and settings.yandex_folder_id:
        return YandexFoundationTextProvider(settings)
    return StubTextGenerationProvider()
