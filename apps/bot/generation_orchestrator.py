"""Фоновая генерация и доставка (M5): картинки, поздравления, VK."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from apps.bot.max_client import MaxBotClient
from packages.db.models import GenerationJob, StoredFile, UsageEvent, User
from packages.domain.text_generation import TextGenerationOutput
from packages.greeting.intents import (
    build_greeting_card_image_prompt,
    greeting_system_prompt,
    infer_greeting_intent,
    vk_post_image_prompt_from_post,
)
from packages.media.watermark import apply_watermark_if_needed
from packages.providers.image_generation import ImageGenerationPort
from packages.providers.text_generation import TextGenerationPort
from packages.referrals.service import ReferralService
from packages.shared.settings import Settings
from packages.stars.service import StarsLedgerService
from packages.storage.interface import FileStoragePort

logger = logging.getLogger(__name__)

USER_IMG_FAIL = (
    "К сожалению, картинку сгенерировать не получилось. Попробуйте позже или измените описание."
)


def _usage_event_kind(context_kind: str | None) -> str:
    m = {
        "consumer_image": "consumer_image_intake",
        "business_image": "business_image_intake",
        "greeting_image": "text_greeting",
        "vk_post_image": "text_vk_post",
    }
    return m.get(context_kind or "", "consumer_image_intake")


class GenerationOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: Any,
        text_port: TextGenerationPort,
        image_port: ImageGenerationPort,
        storage: FileStoragePort,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._text = text_port
        self._image = image_port
        self._storage = storage
        self._stars = StarsLedgerService()
        self._referrals = ReferralService(self._stars)

    async def run_image_job_after_commit(
        self,
        job_id: int,
        max_user_id: int,
        client: MaxBotClient,
        *,
        mode: str = "consumer",
        followup_menu: list[dict[str, Any]] | None = None,
    ) -> None:
        _ = mode
        correlation = ""
        try:
            async with self._session_factory() as session:
                job = await session.get(GenerationJob, job_id)
                if job is None or job.status != "queued":
                    logger.info(
                        "m5_event=job_skip job_id=%s status=%s",
                        job_id,
                        getattr(job, "status", None),
                    )
                    return
                correlation = job.correlation_id or str(job.id)
                logger.info(
                    "m5_event=generation_requested job_id=%s correlation_id=%s context_kind=%s",
                    job.id,
                    correlation,
                    job.context_kind,
                )
                job.status = "processing"
                await session.flush()

                logger.info(
                    "m5_event=provider_call_started job_id=%s correlation_id=%s provider_kind=%s",
                    job.id,
                    correlation,
                    self._image.__class__.__name__,
                )
                res = await self._image.generate(
                    prompt=job.prompt,
                    correlation_id=correlation,
                    meta={"context_kind": job.context_kind, "job_id": job.id},
                )
                logger.info(
                    "m5_event=provider_call_finished job_id=%s correlation_id=%s ok=%s",
                    job.id,
                    correlation,
                    res.ok,
                )

                if not res.ok or not res.image_bytes:
                    job.status = "failed"
                    job.error_message = (res.error_code or "generation_failed")[:2000]
                    job.provider_meta = {"safe": res.safe_meta, "error": res.error_code}
                    job.provider = res.provider
                    meta = dict(job.meta or {})
                    await session.commit()
                    await self._notify_partial_on_image_failure(
                        client, max_user_id, job.context_kind, meta
                    )
                    if job.context_kind not in ("greeting_image", "vk_post_image"):
                        await client.send_message(user_id=max_user_id, text=USER_IMG_FAIL)
                    logger.warning(
                        "m5_event=generation_failed job_id=%s correlation_id=%s code=%s",
                        job.id,
                        correlation,
                        res.error_code,
                    )
                    return

                final_bytes, wm_meta = apply_watermark_if_needed(
                    res.image_bytes,
                    mime_type=res.mime_type,
                    watermark_required=job.watermark_required,
                    settings=self._settings,
                )
                out_mime = "image/png" if wm_meta.get("watermark_applied") else res.mime_type
                backend, key = await self._storage.save_bytes(
                    data=final_bytes, mime_type=out_mime, meta_hint={"job_id": job.id}
                )
                sha = hashlib.sha256(final_bytes).hexdigest()
                sf = StoredFile(
                    generation_job_id=job.id,
                    storage_backend=backend,
                    storage_key=key,
                    mime_type=out_mime,
                    byte_size=len(final_bytes),
                    sha256_hex=sha,
                    meta={
                        **wm_meta,
                        "provider": res.provider,
                        "correlation_id": correlation,
                    },
                )
                session.add(sf)
                job.status = "succeeded"
                job.provider = res.provider
                job.provider_meta = {
                    "provider_safe": res.safe_meta,
                    "watermark": {"applied": bool(wm_meta.get("watermark_applied"))},
                }
                job.error_message = None
                ukind = _usage_event_kind(job.context_kind)
                session.add(
                    UsageEvent(
                        user_id=job.user_id,
                        kind=ukind,
                        units=1,
                        meta={
                            "job_id": job.id,
                            "correlation_id": correlation,
                            "context_kind": job.context_kind,
                        },
                    )
                )
                u = await session.get(User, job.user_id)
                if u:
                    await self._referrals.try_reward_on_first_image_flow(session, u)
                meta_snapshot = dict(job.meta or {})
                ctx_kind = job.context_kind or ""
                jid = job.id
                await session.commit()

                logger.info(
                    "m5_event=output_stored job_id=%s correlation_id=%s bytes=%s",
                    jid,
                    correlation,
                    len(final_bytes),
                )

                await self._deliver_image_bundle(
                    client=client,
                    max_user_id=max_user_id,
                    context_kind=ctx_kind,
                    job_meta=meta_snapshot,
                    image_bytes=final_bytes,
                    image_mime=out_mime,
                    job_id=jid,
                    correlation_id=correlation,
                )
                if followup_menu:
                    await client.send_message(
                        user_id=max_user_id,
                        text="Что дальше?",
                        attachments=followup_menu,
                    )
        except Exception:
            logger.exception(
                "m5_event=generation_exception job_id=%s correlation_id=%s",
                job_id,
                correlation,
            )
            try:
                await client.send_message(
                    user_id=max_user_id,
                    text="Произошла ошибка при генерации. Попробуйте позже.",
                )
            except Exception:
                pass

    async def _notify_partial_on_image_failure(
        self,
        client: MaxBotClient,
        max_user_id: int,
        context_kind: str | None,
        meta: dict[str, Any],
    ) -> None:
        if context_kind == "greeting_image":
            t = meta.get("greeting_text")
            if t:
                await client.send_message(user_id=max_user_id, text=t)
                await client.send_message(
                    user_id=max_user_id,
                    text="Открытку сгенерировать не получилось — квота за это поздравление не списана.",
                )
        elif context_kind == "vk_post_image":
            t = meta.get("vk_post_text")
            if t:
                await client.send_message(user_id=max_user_id, text=t, fmt="markdown")
                await client.send_message(
                    user_id=max_user_id,
                    text=(
                        "Картинку к посту сделать не вышло — пост выше можно использовать без картинки. "
                        "Квота не списана."
                    ),
                )

    async def _deliver_image_bundle(
        self,
        *,
        client: MaxBotClient,
        max_user_id: int,
        context_kind: str,
        job_meta: dict[str, Any],
        image_bytes: bytes,
        image_mime: str,
        job_id: int,
        correlation_id: str,
    ) -> None:
        if context_kind == "greeting_image":
            gt = job_meta.get("greeting_text") or ""
            await client.send_message(user_id=max_user_id, text=gt)
            ok = await client.send_message_with_image(
                user_id=max_user_id,
                text="А вот открытка:",
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
        elif context_kind == "vk_post_image":
            pt = job_meta.get("vk_post_text") or ""
            await client.send_message(user_id=max_user_id, text=pt, fmt="markdown")
            ok = await client.send_message_with_image(
                user_id=max_user_id,
                text="Иллюстрация для поста:",
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
        else:
            ok = await client.send_message_with_image(
                user_id=max_user_id,
                text="Готово — вот ваша картинка:",
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
        logger.info(
            "m5_event=output_delivered job_id=%s correlation_id=%s ok=%s context=%s",
            job_id,
            correlation_id,
            ok,
            context_kind,
        )

    async def run_greeting_bundle_after_commit(
        self,
        *,
        max_user_id: int,
        internal_user_id: int,
        conversation_id: int | None,
        raw_prompt: str,
        wm_required: bool,
        client: MaxBotClient,
        followup_menu: list[dict[str, Any]] | None,
    ) -> None:
        correlation_id = str(uuid.uuid4())
        logger.info(
            "m5_event=greeting_bundle_started correlation_id=%s max_user_id=%s",
            correlation_id,
            max_user_id,
        )
        try:
            intent = infer_greeting_intent(raw_prompt)
            sys_p = greeting_system_prompt(intent)
            up = f"Пожелания пользователя:\n{raw_prompt}"
            t_out: TextGenerationOutput = await self._text.generate(system_prompt=sys_p, user_prompt=up)
            if not t_out.ok:
                await client.send_message(user_id=max_user_id, text=t_out.text)
                logger.warning(
                    "m5_event=greeting_text_failed correlation_id=%s code=%s",
                    correlation_id,
                    t_out.error_code,
                )
                return
            img_prompt = build_greeting_card_image_prompt(raw_prompt, intent)
            async with self._session_factory() as session:
                job = GenerationJob(
                    user_id=internal_user_id,
                    conversation_id=conversation_id,
                    feature_type="image",
                    context_kind="greeting_image",
                    correlation_id=correlation_id,
                    status="queued",
                    prompt=img_prompt,
                    watermark_required=wm_required,
                    provider="stub",
                    meta={
                        "greeting_text": t_out.text,
                        "user_prompt": raw_prompt[:800],
                        "intent": intent,
                    },
                )
                session.add(job)
                await session.flush()
                jid = job.id
                await session.commit()
            await self.run_image_job_after_commit(
                jid, max_user_id, client, mode="consumer", followup_menu=followup_menu
            )
        except Exception:
            logger.exception("m5_event=greeting_bundle_exception correlation_id=%s", correlation_id)
            await client.send_message(
                user_id=max_user_id,
                text="Не получилось подготовить поздравление. Попробуйте чуть позже.",
            )

    async def run_vk_bundle_after_commit(
        self,
        *,
        max_user_id: int,
        internal_user_id: int,
        conversation_id: int | None,
        topic: str,
        wm_required: bool,
        client: MaxBotClient,
        followup_menu: list[dict[str, Any]] | None,
    ) -> None:
        correlation_id = str(uuid.uuid4())
        logger.info(
            "m5_event=vk_bundle_started correlation_id=%s max_user_id=%s",
            correlation_id,
            max_user_id,
        )
        try:
            sys_p = (
                "Ты личный маркетолог для малого бизнеса в России. Пишешь короткий пост для VK: "
                "2 варианта заголовка в начале, затем основной текст до ~900 символов, "
                "умеренно эмодзи, понятный призыв."
            )
            t_out = await self._text.generate(system_prompt=sys_p, user_prompt=topic)
            if not t_out.ok:
                await client.send_message(user_id=max_user_id, text=t_out.text)
                return
            img_prompt = vk_post_image_prompt_from_post(t_out.text)
            async with self._session_factory() as session:
                job = GenerationJob(
                    user_id=internal_user_id,
                    conversation_id=conversation_id,
                    feature_type="image",
                    context_kind="vk_post_image",
                    correlation_id=correlation_id,
                    status="queued",
                    prompt=img_prompt,
                    watermark_required=wm_required,
                    provider="stub",
                    meta={
                        "vk_post_text": t_out.text,
                        "original_topic": topic[:800],
                    },
                )
                session.add(job)
                await session.flush()
                jid = job.id
                await session.commit()
            await self.run_image_job_after_commit(
                jid, max_user_id, client, mode="business", followup_menu=followup_menu
            )
        except Exception:
            logger.exception("m5_event=vk_bundle_exception correlation_id=%s", correlation_id)
            await client.send_message(
                user_id=max_user_id,
                text="Не вышло подготовить пост. Попробуйте позже.",
            )
