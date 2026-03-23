"""
M3 сценарии + M4 квоты, paywall, рефералы, звёзды.
Логика вне MAX-транспорта.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import packages.shared.callbacks as cb
import packages.shared.states as st
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
from apps.bot.menus import business_main_menu, consumer_main_menu, mode_selection_keyboard
from apps.bot.paywall import (
    paywall_keyboard,
    paywall_text_image_quota,
    paywall_text_text_quota,
    paywall_text_vk_not_entitled,
    paywall_text_vk_quota,
)
from packages.billing.stub_service import StubBillingCheckoutService
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
from packages.shared.settings import Settings
from packages.stars.service import StarsLedgerService

logger = logging.getLogger(__name__)


class StateMachineService:
    def __init__(
        self,
        text: TextGenerationPort,
        billing: StubBillingCheckoutService,
        settings: Settings,
    ) -> None:
        self._text = text
        self._billing = billing
        self._settings = settings
        self._ent = EntitlementService(settings)
        self._stars = StarsLedgerService()
        self._referrals = ReferralService(self._stars)

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
            text = "Сейчас это действие недоступно по правилам тарифа."
        await client.send_message(
            user_id=max_uid,
            text=text,
            fmt="markdown",
            attachments=paywall_keyboard(),
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
            text=(
                "Здравствуйте! Я помогу с текстами и заявками на картинки.\n"
                "Всё управление — кнопками ниже, без команд со слэшем.\n"
                "Сначала выберите, для кого бот:"
            ),
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
                text="Выберите режим кнопками:",
                attachments=mode_selection_keyboard(),
            )
            return

        if conv.flow_state == st.AWAIT_REFERRAL_CODE:
            if not text.strip():
                await client.send_message(user_id=max_uid, text="Введите код одним сообщением (как вам дали).")
                return
            ok, reason = await self._referrals.attach_by_code(session, user, text.strip())
            conv.flow_state = st.IDLE
            conv.flow_data = None
            if ok:
                await client.send_message(user_id=max_uid, text="Код принят! Спасибо, что пришли по приглашению.")
            else:
                msgs = {
                    "already_attached": "У вас уже указан пригласивший.",
                    "unknown_code": "Такого кода нет. Проверьте и попробуйте снова.",
                    "self_referral": "Нельзя использовать свой код.",
                    "invitee_already_has_referral": "Приглашение уже было учтено ранее.",
                }
                await client.send_message(
                    user_id=max_uid,
                    text=msgs.get(reason, "Не получилось применить код."),
                )
            menu = (
                consumer_main_menu()
                if user.current_mode == "consumer"
                else business_main_menu()
            )
            await client.send_message(user_id=max_uid, text="Меню:", attachments=menu)
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
                    text="Выберите действие кнопками в меню — так проще всего.",
                    attachments=menu,
                )
                await self._log_chat(session, conv, "user", text, {"note": "idle_free_text"})
            return

        if conv.flow_state == st.CONSUMER_AWAIT_QUESTION:
            if not text.strip():
                await client.send_message(user_id=max_uid, text="Напишите вопрос текстом, одним сообщением.")
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
            session.add(UsageEvent(user_id=user.id, kind="text_question", units=1, meta={"flow": "consumer"}))
            await self._log_chat(session, conv, "assistant", reply, {"provider": "text"})
            await client.send_message(user_id=max_uid, text=reply)
            await client.send_message(
                user_id=max_uid,
                text="Что дальше?",
                attachments=consumer_main_menu(),
            )
            return

        if conv.flow_state == st.CONSUMER_AWAIT_GREETING_PROMPT:
            if not text.strip():
                await client.send_message(
                    user_id=max_uid,
                    text="Опишите одним сообщением: для кого и какой повод (например: маме на день рождения).",
                )
                return
            chk = await self._ent.can_start_consumer_greeting_flow(session, user)
            if not chk.allowed:
                await self._send_paywall_for_decision(client, max_uid, chk)
                conv.flow_state = st.IDLE
                return
            await self._log_chat(session, conv, "user", text, {"flow": st.CONSUMER_AWAIT_GREETING_PROMPT})
            sys_p = (
                "Ты помогаешь составлять тёплые поздравления для близких. Язык простой, искренний, без клише."
            )
            user_p = f"Составь поздравление по этим пожеланиям:\n{text}"
            reply = await self._text.generate(system_prompt=sys_p, user_prompt=user_p)
            conv.flow_state = st.IDLE
            conv.flow_data = None
            session.add(UsageEvent(user_id=user.id, kind="text_greeting", units=1, meta={"flow": "consumer"}))
            await self._referrals.try_reward_on_first_image_flow(session, user)
            await self._log_chat(session, conv, "assistant", reply, {"provider": "text"})
            await client.send_message(user_id=max_uid, text=reply)
            await client.send_message(
                user_id=max_uid,
                text="Могу помочь ещё — выберите в меню:",
                attachments=consumer_main_menu(),
            )
            return

        if conv.flow_state == st.BUSINESS_AWAIT_VK_POST_PROMPT:
            if not text.strip():
                await client.send_message(
                    user_id=max_uid,
                    text="Опишите тему или акцию для поста одним сообщением (что рекламируем, сроки, тон).",
                )
                return
            chk = await self._ent.can_start_business_vk_flow(session, user)
            if not chk.allowed:
                await self._send_paywall_for_decision(client, max_uid, chk)
                conv.flow_state = st.IDLE
                return
            await self._log_chat(session, conv, "user", text, {"flow": st.BUSINESS_AWAIT_VK_POST_PROMPT})
            sys_p = (
                "Ты личный маркетолог для малого бизнеса в России. Пишешь посты для VK: структура, эмодзи умеренно, "
                "понятный призыв. 2–3 варианта заголовка в начале, затем основной текст до ~1200 символов."
            )
            reply = await self._text.generate(system_prompt=sys_p, user_prompt=text)
            conv.flow_state = st.IDLE
            conv.flow_data = None
            session.add(UsageEvent(user_id=user.id, kind="text_vk_post", units=1, meta={"flow": "business"}))
            await self._log_chat(session, conv, "assistant", reply, {"provider": "text"})
            await client.send_message(user_id=max_uid, text=reply)
            await client.send_message(
                user_id=max_uid,
                text="Ещё задачи — в меню:",
                attachments=business_main_menu(),
            )
            return

        if conv.flow_state in (st.CONSUMER_AWAIT_IMAGE_PROMPT, st.BUSINESS_AWAIT_IMAGE_PROMPT):
            if not text.strip():
                await client.send_message(
                    user_id=max_uid,
                    text="Опишите картинку одним сообщением: что должно быть на изображении.",
                )
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
            job = GenerationJob(
                user_id=user.id,
                conversation_id=conv.id,
                feature_type="image",
                provider="stub",
                status="placeholder",
                prompt=text,
                watermark_required=self._ent.watermark_for_next_image_job(plan),
            )
            session.add(job)
            await session.flush()
            conv.flow_state = st.IDLE
            conv.flow_data = None
            ukind = "consumer_image_intake" if mode == "consumer" else "business_image_intake"
            session.add(UsageEvent(user_id=user.id, kind=ukind, units=1, meta={"mode": mode}))
            await self._referrals.try_reward_on_first_image_flow(session, user)
            wm = "Да (тариф free)" if job.watermark_required else "Нет (платный тариф)"
            ack = (
                "Заявка на картинку принята.\n"
                f"Номер заявки: {job.id}\n"
                f"Водяной знак по тарифу: {wm}\n"
                "Описание сохранено; генерация изображения подключится позже."
            )
            await self._log_chat(session, conv, "assistant", ack, {"job_id": job.id})
            await client.send_message(user_id=max_uid, text=ack)
            menu = consumer_main_menu() if mode == "consumer" else business_main_menu()
            await client.send_message(user_id=max_uid, text="Что дальше?", attachments=menu)
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
            cb.is_v1_paywall_action(segments, "subscribe"),
            cb.is_v1_paywall_action(segments, "invite"),
            cb.is_v1_paywall_action(segments, "enter_code"),
        )
        if not any(paywall_actions):
            return False
        if cb.is_v1_paywall_action(segments, "subscribe"):
            if cid:
                await client.answer_callback(callback_id=cid, notification="Подписка")
            plan = self._plan_for_checkout(user)
            cs = await self._billing.create_checkout_session(
                user_id=user.id, plan_code=plan, success_return_url=None
            )
            await client.send_message(
                user_id=max_uid,
                text=(
                    f"{self._billing.subscription_ux_message()}\n\n"
                    f"Тестовая ссылка (stub): {cs.payment_url}\n"
                    f"План: `{cs.plan_code}`"
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
                text="Отправьте **код приглашения** одним сообщением (формат R-XXXXXXXX).",
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
                    text=(
                        "Режим «для себя»: поздравления и картинки.\n"
                        "Дальше всё просто — нажимайте кнопки. Что сделаем?"
                    ),
                    attachments=consumer_main_menu(),
                )
            else:
                await client.send_message(
                    user_id=max_uid,
                    text=(
                        "Режим «для бизнеса»: ваш **личный маркетолог** в MAX.\n"
                        "Посты для VK и картинки — по тарифу. Выберите действие кнопкой."
                    ),
                    fmt="markdown",
                    attachments=business_main_menu(),
                )
            return

        if user.current_mode is None:
            if cid:
                await client.answer_callback(callback_id=cid, notification="Сначала выберите режим")
            await client.send_message(
                user_id=max_uid,
                text="Сначала выберите режим «для себя» или «для бизнеса».",
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

        if user.current_mode == "consumer" and segments == ["consumer", "enter_referral_code"]:
            conv.flow_state = st.AWAIT_REFERRAL_CODE
            if cid:
                await client.answer_callback(callback_id=cid, notification="Код")
            await client.send_message(
                user_id=max_uid,
                text="Отправьте код приглашения одним сообщением.",
            )
            return
        if user.current_mode == "business" and segments == ["business", "enter_referral_code"]:
            conv.flow_state = st.AWAIT_REFERRAL_CODE
            if cid:
                await client.answer_callback(callback_id=cid, notification="Код")
            await client.send_message(
                user_id=max_uid,
                text="Отправьте код приглашения одним сообщением.",
            )
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
                    text="Напишите **одним сообщением**, что вас интересует. Я отвечу простым языком.",
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
                    text="Опишите **одним сообщением**, какую картинку хотите (предмет, стиль, настроение).",
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
                    text=(
                        "**Поздравление:** одним сообщением напишите, для кого и какой повод "
                        "(например: зятю на юбилей 60 лет, тёплый тон)."
                    ),
                    fmt="markdown",
                )
                return
            if cb.is_v1_consumer_action(segments, "my_stars"):
                bal = await self._stars_balance(session, user.id)
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Звёзды")
                await client.send_message(
                    user_id=max_uid,
                    text=f"У вас **{bal}** звёзд (по журналу начислений).",
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
                await client.send_message(
                    user_id=max_uid,
                    text=f"{self._billing.subscription_ux_message()}\n\nStub: {cs.payment_url}",
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
                    text=(
                        "**Пост для VK:** одним сообщением опишите, о чём пост "
                        "(товар, акция, праздник, адрес, сроки — что важно)."
                    ),
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
                    text="Опишите **одним сообщением** картинку для бизнеса (логотип, товар, баннер и т.п.).",
                    fmt="markdown",
                )
                return
            if cb.is_v1_business_action(segments, "my_stars"):
                bal = await self._stars_balance(session, user.id)
                if cid:
                    await client.answer_callback(callback_id=cid, notification="Звёзды")
                await client.send_message(
                    user_id=max_uid,
                    text=f"У вас **{bal}** звёзд.",
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
                await client.send_message(
                    user_id=max_uid,
                    text=f"{self._billing.subscription_ux_message()}\n\nStub: {cs.payment_url}",
                    attachments=business_main_menu(),
                )
                return

        if cid:
            await client.answer_callback(callback_id=cid, notification="Неизвестная кнопка")
