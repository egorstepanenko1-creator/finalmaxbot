"""
M3 сценарии + M4 квоты, paywall + M5 генерация и доставка.
Логика вне MAX-транспорта.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import packages.shared.callbacks as cb
import packages.shared.states as st
from apps.bot.generation_orchestrator import GenerationOrchestrator
from apps.bot.max_client import MaxBotClient
from apps.bot.max_payload import (
    extract_bot_started_user_id,
    extract_callback_id,
    extract_callback_payload,
    extract_callback_user_id,
    extract_message_from_update,
    extract_message_text,
    extract_sender_user_id,
)
from apps.bot.menus import (
    business_main_menu,
    business_quick_start_keyboard,
    business_templates_keyboard,
    consumer_main_menu,
    consumer_quick_start_keyboard,
    consumer_templates_keyboard,
    mode_selection_keyboard,
)
from apps.bot.paywall import (
    paywall_keyboard,
    paywall_text_image_quota,
    paywall_text_text_quota,
    paywall_text_vk_not_entitled,
    paywall_text_vk_quota,
)
from packages.billing.interfaces import BillingPort
from packages.billing.max_notices import notice_subscription_cancelled
from packages.content.templates_ru import get_business_template, get_consumer_template
from packages.db.models import (
    ChatMessage,
    Conversation,
    GenerationJob,
    UsageEvent,
    User,
)
from packages.entitlements.service import EntitlementDecision, EntitlementService
from packages.providers.text_generation import TextGenerationPort
from packages.referrals.service import ReferralService
from packages.shared import user_copy_ru as ru
from packages.shared.settings import Settings
from packages.stars.service import StarsLedgerService

logger = logging.getLogger(__name__)


class StateMachineService:
    def __init__(
        self,
        text: TextGenerationPort,
        billing: BillingPort,
        settings: Settings,
        orchestrator: GenerationOrchestrator,
        after_commit: list[Any],
    ) -> None:
        self._text = text
        self._billing = billing
        self._settings = settings
        self._orch = orchestrator
        self._after_commit = after_commit
        self._ent = EntitlementService(settings)
        self._stars = StarsLedgerService()
        self._referrals = ReferralService(self._stars)

    def _enqueue_after_commit(self, factory: Any) -> None:
        """factory: lambda, вызов которого возвращает awaitable (coroutine)."""
        self._after_commit.append(factory)

    async def _load_user(self, session: Any, max_user_id: int) -> User | None:
        r = await session.execute(
            select(User)
            .where(User.max_user_id == max_user_id)
            .options(selectinload(User.conversation))
        )
        return r.scalar_one_or_none()

    async def _get_or_create_user(self, session: Any, max_user_id: int) -> User:
        u = await self._load_user(session, max_user_id)
        if u:
            return u
        u = User(max_user_id=max_user_id, current_mode=None, onboarding_state="new")
        session.add(u)
        await session.flush()
        await session.refresh(u)
        return u

    async def _ensure_conversation(self, session: Any, user: User) -> Conversation:
        r = await session.execute(select(Conversation).where(Conversation.user_id == user.id))
        existing = r.scalar_one_or_none()
        if existing:
            return existing
        c = Conversation(user_id=user.id, flow_state=st.IDLE, flow_data=None)
        session.add(c)
        await session.flush()
        return c

    async def _log_chat(
        self, session: Any, conv: Conversation, role: str, content: str, extra: dict | None = None
    ) -> None:
        session.add(
            ChatMessage(conversation_id=conv.id, role=role, content=content, extra=extra)
        )

    async def _stars_balance(self, session: Any, internal_user_id: int) -> int:
        return await self._stars.balance_sum(session, internal_user_id)

    def _plan_for_checkout(self, user: User) -> str:
        if user.current_mode == "business":
            return "business_marketer_490"
        return "consumer_plus_290"

    async def _send_paywall_for_decision(
        self,
        client: MaxBotClient,
        max_uid: int,
        d: EntitlementDecision,
    ) -> None:
        if d.reason in (
            "image_quota_exhausted",
            "business_free_image_quota",
            "business_image_quota_exhausted",
        ):
            text = paywall_text_image_quota(
                used=int(d.detail.get("used", 0)),
                limit=int(d.detail.get("limit", 0)),
            )
        elif d.reason == "text_quota_exhausted":
            text = paywall_text_text_quota(
                used=int(d.detail.get("used", 0)),
                limit=int(d.detail.get("limit", 0)),
            )
        elif d.reason == "vk_not_entitled":
            text = paywall_text_vk_not_entitled()
        elif d.reason == "vk_quota_exhausted":
            text = paywall_text_vk_quota(
                used=int(d.detail.get("used", 0)),
                limit=int(d.detail.get("limit", 0)),
            )
        else:
            text = ru.PAYWALL_GENERIC
        await client.send_message(
            user_id=max_uid,
            text=text,
            fmt="markdown",
            attachments=paywall_keyboard(),
        )

    async def _handle_consumer_template_pick(
        self,
        session: Any,
        client: MaxBotClient,
        user: User,
        conv: Conversation,
        max_uid: int,
        slug: str,
        cid: str | None,
    ) -> None:
        tpl = get_consumer_template(slug)
        if tpl is None:
            if cid:
                await client.answer_callback(callback_id=cid, notification="Нет шаблона")
            return
        if tpl.flow_kind == "greeting":
            d = await self._ent.can_start_consumer_greeting_flow(session, user)
            if not d.allowed:
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Лимит")
                await self._send_paywall_for_decision(client, max_uid, d)
                return
            conv.flow_state = st.CONSUMER_AWAIT_GREETING_PROMPT
        elif tpl.flow_kind == "image":
            d = await self._ent.can_start_consumer_image_flow(session, user)
            if not d.allowed:
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Лимит")
                await self._send_paywall_for_decision(client, max_uid, d)
                return
            conv.flow_state = st.CONSUMER_AWAIT_IMAGE_PROMPT
        else:
            return
        if cid:
            await client.answer_callback(callback_id=cid, notification="Шаблон")
        await client.send_message(
            user_id=max_uid,
            text=ru.TEMPLATE_FOLLOWUP.format(draft=tpl.draft),
            fmt="markdown",
            attachments=consumer_main_menu(),
        )

    async def _handle_business_template_pick(
        self,
        session: Any,
        client: MaxBotClient,
        user: User,
        conv: Conversation,
        max_uid: int,
        slug: str,
        cid: str | None,
    ) -> None:
        tpl = get_business_template(slug)
        if tpl is None:
            if cid:
                await client.answer_callback(callback_id=cid, notification="Нет шаблона")
            return
        if tpl.flow_kind == "vk":
            d = await self._ent.can_start_business_vk_flow(session, user)
            if not d.allowed:
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Недоступно")
                await self._send_paywall_for_decision(client, max_uid, d)
                return
            conv.flow_state = st.BUSINESS_AWAIT_VK_POST_PROMPT
        elif tpl.flow_kind == "image":
            d = await self._ent.can_start_business_image_flow(session, user)
            if not d.allowed:
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Лимит")
                await self._send_paywall_for_decision(client, max_uid, d)
                return
            conv.flow_state = st.BUSINESS_AWAIT_IMAGE_PROMPT
        else:
            return
        if cid:
            await client.answer_callback(callback_id=cid, notification="Шаблон")
        await client.send_message(
            user_id=max_uid,
            text=ru.TEMPLATE_FOLLOWUP.format(draft=tpl.draft),
            fmt="markdown",
            attachments=business_main_menu(),
        )

    async def on_bot_started(
        self, update: dict[str, Any], session: Any, client: MaxBotClient
    ) -> None:
        uid = extract_bot_started_user_id(update)
        if uid is None:
            logger.warning("bot_started without user_id: %s", update)
            return
        user = await self._get_or_create_user(session, uid)
        await self._ensure_conversation(session, user)
        await client.send_message(
            user_id=uid,
            text=f"{ru.WELCOME}\n\n{ru.MODE_SELECT_NUDGE}",
            fmt="markdown",
            attachments=mode_selection_keyboard(),
        )

    async def on_message_created(
        self, update: dict[str, Any], session: Any, client: MaxBotClient
    ) -> None:
        msg = extract_message_from_update(update)
        if not msg:
            return
        max_uid = extract_sender_user_id(msg)
        if max_uid is None:
            return
        user = await self._get_or_create_user(session, max_uid)
        conv = await self._ensure_conversation(session, user)
        text = extract_message_text(msg) or ""

        if user.current_mode is None:
            await client.send_message(
                user_id=max_uid,
                text=ru.MODE_SELECT_NUDGE,
                fmt="markdown",
                attachments=mode_selection_keyboard(),
            )
            return

        if conv.flow_state == st.AWAIT_REFERRAL_CODE:
            if not text.strip():
                await client.send_message(user_id=max_uid, text=ru.REFERRAL_CODE_EMPTY)
                return
            ok, reason = await self._referrals.attach_by_code(session, user, text.strip())
            conv.flow_state = st.IDLE
            conv.flow_data = None
            if ok:
                await client.send_message(user_id=max_uid, text=ru.REFERRAL_MESSAGES["accepted"])
            else:
                await client.send_message(
                    user_id=max_uid,
                    text=ru.REFERRAL_MESSAGES.get(reason, ru.REFERRAL_MESSAGES["default_fail"]),
                )
            menu = (
                consumer_main_menu()
                if user.current_mode == "consumer"
                else business_main_menu()
            )
            await client.send_message(user_id=max_uid, text=ru.MENU_AFTER_REFERRAL, attachments=menu)
            return

        if conv.flow_state == st.IDLE:
            if text.strip():
                menu = (
                    consumer_main_menu()
                    if user.current_mode == "consumer"
                    else business_main_menu()
                )
                await client.send_message(
                    user_id=max_uid,
                    text=ru.IDLE_CHOOSE_BUTTONS,
                    attachments=menu,
                )
                await self._log_chat(session, conv, "user", text, {"note": "idle_free_text"})
            return

        if conv.flow_state == st.CONSUMER_AWAIT_QUESTION:
            if not text.strip():
                await client.send_message(user_id=max_uid, text=ru.QUESTION_EMPTY)
                return
            chk = await self._ent.can_complete_text_question(session, user)
            if not chk.allowed:
                await self._send_paywall_for_decision(client, max_uid, chk)
                conv.flow_state = st.IDLE
                return
            await self._log_chat(session, conv, "user", text, {"flow": st.CONSUMER_AWAIT_QUESTION})
            sys_p = (
                "Ты дружелюбный помощник для людей 50+. Отвечай по-русски коротко, ясно, без канцелярита."
            )
            reply = await self._text.generate(system_prompt=sys_p, user_prompt=text)
            conv.flow_state = st.IDLE
            conv.flow_data = None
            if not reply.ok:
                await client.send_message(user_id=max_uid, text=reply.text)
                return
            session.add(UsageEvent(user_id=user.id, kind="text_question", units=1, meta={"flow": "consumer"}))
            await self._log_chat(session, conv, "assistant", reply.text, {"provider": reply.provider})
            await client.send_message(user_id=max_uid, text=reply.text)
            await client.send_message(
                user_id=max_uid,
                text=ru.CONSUMER_AFTER_QUESTION,
                attachments=consumer_main_menu(),
            )
            return

        if conv.flow_state == st.CONSUMER_AWAIT_GREETING_PROMPT:
            if not text.strip():
                await client.send_message(user_id=max_uid, text=ru.GREETING_PROMPT, fmt="markdown")
                return
            chk = await self._ent.can_start_consumer_greeting_flow(session, user)
            if not chk.allowed:
                await self._send_paywall_for_decision(client, max_uid, chk)
                conv.flow_state = st.IDLE
                return
            await self._log_chat(session, conv, "user", text, {"flow": st.CONSUMER_AWAIT_GREETING_PROMPT})
            _, plan = await self._ent.evaluate(session, user)
            wm = self._ent.watermark_for_next_image_job(plan)
            conv.flow_state = st.IDLE
            conv.flow_data = None
            menu = consumer_main_menu()
            await client.send_message(user_id=max_uid, text=ru.WORKING_GREETING)
            self._enqueue_after_commit(
                lambda: self._orch.run_greeting_bundle_after_commit(
                    max_user_id=max_uid,
                    internal_user_id=user.id,
                    conversation_id=conv.id,
                    raw_prompt=text,
                    wm_required=wm,
                    client=client,
                    followup_menu=menu,
                )
            )
            return

        if conv.flow_state == st.BUSINESS_AWAIT_VK_POST_PROMPT:
            if not text.strip():
                await client.send_message(user_id=max_uid, text=ru.VK_POST_PROMPT, fmt="markdown")
                return
            chk = await self._ent.can_start_business_vk_flow(session, user)
            if not chk.allowed:
                await self._send_paywall_for_decision(client, max_uid, chk)
                conv.flow_state = st.IDLE
                return
            await self._log_chat(session, conv, "user", text, {"flow": st.BUSINESS_AWAIT_VK_POST_PROMPT})
            _, plan = await self._ent.evaluate(session, user)
            wm = self._ent.watermark_for_next_image_job(plan)
            conv.flow_state = st.IDLE
            conv.flow_data = None
            menu = business_main_menu()
            await client.send_message(user_id=max_uid, text=ru.WORKING_VK)
            self._enqueue_after_commit(
                lambda: self._orch.run_vk_bundle_after_commit(
                    max_user_id=max_uid,
                    internal_user_id=user.id,
                    conversation_id=conv.id,
                    topic=text,
                    wm_required=wm,
                    client=client,
                    followup_menu=menu,
                )
            )
            return

        if conv.flow_state in (st.CONSUMER_AWAIT_IMAGE_PROMPT, st.BUSINESS_AWAIT_IMAGE_PROMPT):
            if not text.strip():
                _img_hint = (
                    ru.CREATE_IMAGE_CONSUMER_PROMPT
                    if conv.flow_state == st.CONSUMER_AWAIT_IMAGE_PROMPT
                    else ru.CREATE_IMAGE_BUSINESS_PROMPT
                )
                await client.send_message(user_id=max_uid, text=_img_hint, fmt="markdown")
                return
            mode = "consumer" if conv.flow_state == st.CONSUMER_AWAIT_IMAGE_PROMPT else "business"
            if mode == "consumer":
                chk = await self._ent.can_start_consumer_image_flow(session, user)
            else:
                chk = await self._ent.can_start_business_image_flow(session, user)
            if not chk.allowed:
                await self._send_paywall_for_decision(client, max_uid, chk)
                conv.flow_state = st.IDLE
                return
            _, plan = await self._ent.evaluate(session, user)
            await self._log_chat(session, conv, "user", text, {"flow": conv.flow_state})
            correlation_id = str(uuid.uuid4())
            ctx = "consumer_image" if mode == "consumer" else "business_image"
            job = GenerationJob(
                user_id=user.id,
                conversation_id=conv.id,
                feature_type="image",
                provider="stub",
                status="queued",
                prompt=text,
                watermark_required=self._ent.watermark_for_next_image_job(plan),
                correlation_id=correlation_id,
                context_kind=ctx,
                meta={"mode": mode},
            )
            session.add(job)
            await session.flush()
            conv.flow_state = st.IDLE
            conv.flow_data = None
            jid = job.id
            menu = consumer_main_menu() if mode == "consumer" else business_main_menu()
            ack = (
                f"Принял описание (заявка №{jid}). Генерирую картинку — обычно до пары минут.\n"
                f"Водяной знак по тарифу: {'да' if job.watermark_required else 'нет'}."
            )
            await self._log_chat(session, conv, "assistant", ack, {"job_id": jid, "correlation_id": correlation_id})
            await client.send_message(user_id=max_uid, text=ack)
            self._enqueue_after_commit(
                lambda: self._orch.run_image_job_after_commit(
                    jid,
                    max_uid,
                    client,
                    mode=mode,
                    followup_menu=menu,
                )
            )
            return

        logger.warning("Unhandled flow_state=%s for user=%s", conv.flow_state, max_uid)

    def _parse_mode_legacy(self, raw: str) -> str | None:
        if raw == "mode:consumer":
            return "consumer"
        if raw == "mode:business":
            return "business"
        return None

    async def _handle_paywall_callbacks(
        self,
        session: Any,
        client: MaxBotClient,
        user: User,
        conv: Conversation,
        max_uid: int,
        segments: list[str],
        cid: str | None,
    ) -> bool:
        paywall_actions = (
            cb.is_paywall_subscribe_variant(segments),
            cb.is_v1_paywall_action(segments, "invite"),
            cb.is_v1_paywall_action(segments, "enter_code"),
        )
        if not any(paywall_actions):
            return False
        if cb.is_paywall_subscribe_variant(segments):
            if cid:
                await client.answer_callback(callback_id=cid, notification="Оплата")
            if cb.is_v1_paywall_action(segments, "subscribe_consumer_plus"):
                plan = "consumer_plus_290"
            elif cb.is_v1_paywall_action(segments, "subscribe_business"):
                plan = "business_marketer_490"
            else:
                plan = self._plan_for_checkout(user)
            cs = await self._billing.create_checkout_session(
                user_id=user.id, plan_code=plan, success_return_url=None
            )
            if not cs.payment_url:
                await client.send_message(
                    user_id=max_uid,
                    text=ru.PAYMENT_LINK_UNAVAILABLE,
                    fmt="markdown",
                    attachments=(
                        consumer_main_menu()
                        if user.current_mode == "consumer"
                        else business_main_menu()
                    ),
                )
                return True
            await client.send_message(
                user_id=max_uid,
                text=(
                    f"{self._billing.subscription_ux_message()}\n\n"
                    f"**Ссылка для оплаты** (Т-Банк, безопасно):\n{cs.payment_url}\n\n"
                    f"Тариф: `{cs.plan_code}`"
                ),
                fmt="markdown",
                attachments=(
                    consumer_main_menu()
                    if user.current_mode == "consumer"
                    else business_main_menu()
                ),
            )
            return True
        if cb.is_v1_paywall_action(segments, "invite"):
            if cid:
                await client.answer_callback(callback_id=cid, notification="Приглашение")
            code = await self._referrals.ensure_referral_code(session, user)
            await client.send_message(
                user_id=max_uid,
                text=self._billing.invite_friend_ux_message(referral_code=code),
                fmt="markdown",
                attachments=(
                    consumer_main_menu()
                    if user.current_mode == "consumer"
                    else business_main_menu()
                ),
            )
            return True
        if cb.is_v1_paywall_action(segments, "enter_code"):
            if cid:
                await client.answer_callback(callback_id=cid, notification="Код")
            conv.flow_state = st.AWAIT_REFERRAL_CODE
            await client.send_message(
                user_id=max_uid,
                text=ru.REFERRAL_CODE_PROMPT,
                fmt="markdown",
            )
            return True
        return False

    async def on_callback(
        self, update: dict[str, Any], session: Any, client: MaxBotClient
    ) -> None:
        cid = extract_callback_id(update)
        raw = extract_callback_payload(update) or ""
        max_uid = extract_callback_user_id(update)
        if max_uid is None:
            return

        user = await self._get_or_create_user(session, max_uid)
        conv = await self._ensure_conversation(session, user)
        ver, segments = cb.parse_payload(raw)

        mode_from_legacy = self._parse_mode_legacy(raw) if ver == "legacy" else None
        mode_from_v1 = None
        if ver == cb.VER and cb.is_v1_mode(segments, "consumer"):
            mode_from_v1 = "consumer"
        elif ver == cb.VER and cb.is_v1_mode(segments, "business"):
            mode_from_v1 = "business"

        chosen_mode = mode_from_legacy or mode_from_v1

        if chosen_mode:
            user.current_mode = chosen_mode
            user.onboarding_state = "mode_set"
            if cid:
                await client.answer_callback(callback_id=cid, notification="Сохранено")
            if chosen_mode == "consumer":
                await client.send_message(
                    user_id=max_uid,
                    text=ru.AFTER_MODE_CONSUMER,
                    fmt="markdown",
                    attachments=consumer_main_menu(),
                )
                await client.send_message(
                    user_id=max_uid,
                    text=ru.FIRST_ACTIONS_CONSUMER_HINT,
                    fmt="markdown",
                    attachments=consumer_quick_start_keyboard(),
                )
            else:
                await client.send_message(
                    user_id=max_uid,
                    text=ru.AFTER_MODE_BUSINESS,
                    fmt="markdown",
                    attachments=business_main_menu(),
                )
                await client.send_message(
                    user_id=max_uid,
                    text=ru.FIRST_ACTIONS_BUSINESS_HINT,
                    fmt="markdown",
                    attachments=business_quick_start_keyboard(),
                )
            return

        if user.current_mode is None:
            if cid:
                await client.answer_callback(callback_id=cid, notification="Сначала выберите режим")
            await client.send_message(
                user_id=max_uid,
                text=ru.MODE_SELECT_NUDGE,
                fmt="markdown",
                attachments=mode_selection_keyboard(),
            )
            return

        if ver == cb.VER and await self._handle_paywall_callbacks(
            session, client, user, conv, max_uid, segments, cid
        ):
            return

        if ver != cb.VER:
            if cid:
                await client.answer_callback(callback_id=cid, notification="Кнопка устарела")
            return

        if user.current_mode == "consumer" and cb.is_v1_consumer_action(segments, "templates_menu"):
            if cid:
                await client.answer_callback(callback_id=cid, notification="Шаблоны")
            await client.send_message(
                user_id=max_uid,
                text=ru.TEMPLATES_MENU_TITLE_CONSUMER,
                fmt="markdown",
                attachments=consumer_templates_keyboard(),
            )
            return
        if user.current_mode == "business" and cb.is_v1_business_action(segments, "templates_menu"):
            if cid:
                await client.answer_callback(callback_id=cid, notification="Шаблоны")
            await client.send_message(
                user_id=max_uid,
                text=ru.TEMPLATES_MENU_TITLE_BUSINESS,
                fmt="markdown",
                attachments=business_templates_keyboard(),
            )
            return

        tpl_sel = cb.parse_template_selection(segments)
        if tpl_sel:
            scope, slug = tpl_sel
            if scope == "consumer" and user.current_mode == "consumer":
                await self._handle_consumer_template_pick(
                    session, client, user, conv, max_uid, slug, cid
                )
                return
            if scope == "business" and user.current_mode == "business":
                await self._handle_business_template_pick(
                    session, client, user, conv, max_uid, slug, cid
                )
                return
            if cid:
                await client.answer_callback(callback_id=cid, notification="Сначала режим")
            await client.send_message(
                user_id=max_uid,
                text=ru.MODE_SELECT_NUDGE,
                fmt="markdown",
                attachments=mode_selection_keyboard(),
            )
            return

        if user.current_mode == "consumer" and segments == ["consumer", "enter_referral_code"]:
            conv.flow_state = st.AWAIT_REFERRAL_CODE
            if cid:
                await client.answer_callback(callback_id=cid, notification="Код")
            await client.send_message(user_id=max_uid, text=ru.REFERRAL_CODE_PROMPT, fmt="markdown")
            return
        if user.current_mode == "business" and segments == ["business", "enter_referral_code"]:
            conv.flow_state = st.AWAIT_REFERRAL_CODE
            if cid:
                await client.answer_callback(callback_id=cid, notification="Код")
            await client.send_message(user_id=max_uid, text=ru.REFERRAL_CODE_PROMPT, fmt="markdown")
            return

        if user.current_mode == "consumer":
            if cb.is_v1_consumer_action(segments, "ask_question"):
                chk = await self._ent.can_complete_text_question(session, user)
                if not chk.allowed:
                    if cid:
                        await client.answer_callback(callback_id=cid, notification="Лимит")
                    await self._send_paywall_for_decision(client, max_uid, chk)
                    return
                conv.flow_state = st.CONSUMER_AWAIT_QUESTION
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Жду вопрос")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.ASK_QUESTION_PROMPT,
                    fmt="markdown",
                )
                return
            if cb.is_v1_consumer_action(segments, "create_image"):
                d = await self._ent.can_start_consumer_image_flow(session, user)
                if not d.allowed:
                    if cid:
                        await client.answer_callback(callback_id=cid, notification="Лимит")
                    await self._send_paywall_for_decision(client, max_uid, d)
                    return
                conv.flow_state = st.CONSUMER_AWAIT_IMAGE_PROMPT
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Жду описание")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.CREATE_IMAGE_CONSUMER_PROMPT,
                    fmt="markdown",
                )
                return
            if cb.is_v1_consumer_action(segments, "make_greeting"):
                d = await self._ent.can_start_consumer_greeting_flow(session, user)
                if not d.allowed:
                    if cid:
                        await client.answer_callback(callback_id=cid, notification="Лимит")
                    await self._send_paywall_for_decision(client, max_uid, d)
                    return
                conv.flow_state = st.CONSUMER_AWAIT_GREETING_PROMPT
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Жду детали")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.GREETING_PROMPT,
                    fmt="markdown",
                )
                return
            if cb.is_v1_consumer_action(segments, "my_stars"):
                bal = await self._stars_balance(session, user.id)
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Звёзды")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.STARS_CONSUMER.format(balance=bal),
                    fmt="markdown",
                    attachments=consumer_main_menu(),
                )
                return
            if cb.is_v1_consumer_action(segments, "invite_friend"):
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Приглашение")
                code = await self._referrals.ensure_referral_code(session, user)
                await client.send_message(
                    user_id=max_uid,
                    text=self._billing.invite_friend_ux_message(referral_code=code),
                    fmt="markdown",
                    attachments=consumer_main_menu(),
                )
                return
            if cb.is_v1_consumer_action(segments, "subscription"):
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Подписка")
                plan = self._plan_for_checkout(user)
                cs = await self._billing.create_checkout_session(
                    user_id=user.id, plan_code=plan, success_return_url=None
                )
                if not cs.payment_url:
                    await client.send_message(
                        user_id=max_uid,
                        text=ru.PAYMENT_LINK_UNAVAILABLE,
                        fmt="markdown",
                        attachments=consumer_main_menu(),
                    )
                    return
                await client.send_message(
                    user_id=max_uid,
                    text=(
                        f"{self._billing.subscription_ux_message()}\n\n"
                        f"**Ссылка на оплату (Т-Банк):**\n{cs.payment_url}\n\n"
                        f"Тариф: `{cs.plan_code}`"
                    ),
                    fmt="markdown",
                    attachments=consumer_main_menu(),
                )
                return
            if cb.is_v1_consumer_action(segments, "cancel_autorenew"):
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Автопродление")
                changed = await self._billing.cancel_subscription(session=session, user_id=user.id)
                if changed:
                    await client.send_message(
                        user_id=max_uid,
                        text=notice_subscription_cancelled(),
                        fmt="markdown",
                        attachments=consumer_main_menu(),
                    )
                else:
                    await client.send_message(
                        user_id=max_uid,
                        text=ru.NO_AUTORENEW_TO_CANCEL,
                        fmt="markdown",
                        attachments=consumer_main_menu(),
                    )
                return

        if user.current_mode == "business":
            if cb.is_v1_business_action(segments, "create_vk_post"):
                d = await self._ent.can_start_business_vk_flow(session, user)
                if not d.allowed:
                    if cid:
                        await client.answer_callback(callback_id=cid, notification="Недоступно")
                    await self._send_paywall_for_decision(client, max_uid, d)
                    return
                conv.flow_state = st.BUSINESS_AWAIT_VK_POST_PROMPT
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Жду тему")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.VK_POST_PROMPT,
                    fmt="markdown",
                )
                return
            if cb.is_v1_business_action(segments, "create_image"):
                d = await self._ent.can_start_business_image_flow(session, user)
                if not d.allowed:
                    if cid:
                        await client.answer_callback(callback_id=cid, notification="Лимит")
                    await self._send_paywall_for_decision(client, max_uid, d)
                    return
                conv.flow_state = st.BUSINESS_AWAIT_IMAGE_PROMPT
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Жду описание")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.CREATE_IMAGE_BUSINESS_PROMPT,
                    fmt="markdown",
                )
                return
            if cb.is_v1_business_action(segments, "my_stars"):
                bal = await self._stars_balance(session, user.id)
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Звёзды")
                await client.send_message(
                    user_id=max_uid,
                    text=ru.STARS_BUSINESS.format(balance=bal),
                    fmt="markdown",
                    attachments=business_main_menu(),
                )
                return
            if cb.is_v1_business_action(segments, "invite_friend"):
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Приглашение")
                code = await self._referrals.ensure_referral_code(session, user)
                await client.send_message(
                    user_id=max_uid,
                    text=self._billing.invite_friend_ux_message(referral_code=code),
                    fmt="markdown",
                    attachments=business_main_menu(),
                )
                return
            if cb.is_v1_business_action(segments, "subscription"):
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Подписка")
                plan = self._plan_for_checkout(user)
                cs = await self._billing.create_checkout_session(
                    user_id=user.id, plan_code=plan, success_return_url=None
                )
                if not cs.payment_url:
                    await client.send_message(
                        user_id=max_uid,
                        text=ru.PAYMENT_LINK_UNAVAILABLE,
                        fmt="markdown",
                        attachments=business_main_menu(),
                    )
                    return
                await client.send_message(
                    user_id=max_uid,
                    text=(
                        f"{self._billing.subscription_ux_message()}\n\n"
                        f"**Ссылка на оплату (Т-Банк):**\n{cs.payment_url}\n\n"
                        f"Тариф: `{cs.plan_code}`"
                    ),
                    fmt="markdown",
                    attachments=business_main_menu(),
                )
                return
            if cb.is_v1_business_action(segments, "cancel_autorenew"):
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Автопродление")
                changed = await self._billing.cancel_subscription(session=session, user_id=user.id)
                if changed:
                    await client.send_message(
                        user_id=max_uid,
                        text=notice_subscription_cancelled(),
                        fmt="markdown",
                        attachments=business_main_menu(),
                    )
                else:
                    await client.send_message(
                        user_id=max_uid,
                        text=ru.NO_AUTORENEW_TO_CANCEL,
                        fmt="markdown",
                        attachments=business_main_menu(),
                    )
                return

        if cid:
            await client.answer_callback(callback_id=cid, notification="Неизвестная кнопка")
