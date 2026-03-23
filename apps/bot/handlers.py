from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.bot.max_client import MaxBotClient
from apps.bot.max_payload import (
    extract_bot_started_user_id,
    extract_callback_id,
    extract_callback_payload,
    extract_callback_user_id,
    extract_message_from_update,
    extract_message_text,
    extract_sender_user_id,
    extract_update_type,
)
from packages.db.models import User

logger = logging.getLogger(__name__)

MODE_KEYBOARD: list[dict[str, Any]] = [
    {
        "type": "inline_keyboard",
        "payload": {
            "buttons": [
                [
                    {
                        "type": "callback",
                        "text": "Для себя",
                        "payload": "mode:consumer",
                    },
                    {
                        "type": "callback",
                        "text": "Для бизнеса",
                        "payload": "mode:business",
                    },
                ]
            ]
        },
    }
]


async def _get_or_create_user(session: AsyncSession, max_user_id: int) -> User:
    r = await session.execute(select(User).where(User.max_user_id == max_user_id))
    row = r.scalar_one_or_none()
    if row:
        return row
    u = User(max_user_id=max_user_id, current_mode=None, onboarding_state="new")
    session.add(u)
    await session.flush()
    return u


async def _prompt_mode(client: MaxBotClient, user_id: int) -> None:
    await client.send_message(
        user_id=user_id,
        text="Выберите, как вы пользуетесь ботом:",
        attachments=MODE_KEYBOARD,
    )


async def handle_max_update(
    update: dict[str, Any],
    *,
    session: AsyncSession,
    client: MaxBotClient,
) -> None:
    ut = extract_update_type(update)
    if not ut:
        logger.debug("MAX update without update_type: %s", update)
        return

    if ut == "message_created":
        msg = extract_message_from_update(update)
        if not msg:
            return
        uid = extract_sender_user_id(msg)
        if uid is None:
            logger.warning("message_created without sender user_id")
            return
        user = await _get_or_create_user(session, uid)
        text = extract_message_text(msg)
        if user.current_mode is None:
            await _prompt_mode(client, uid)
            await session.commit()
            return
        if text:
            await client.send_message(
                user_id=uid,
                text=f"Режим: {user.current_mode}. Вы написали: {text}",
            )
        await session.commit()
        return

    if ut == "message_callback":
        cid = extract_callback_id(update)
        payload = extract_callback_payload(update) or ""
        uid = extract_callback_user_id(update)
        if uid is None:
            logger.warning("message_callback without user_id")
            return
        user = await _get_or_create_user(session, uid)
        if payload == "mode:consumer":
            user.current_mode = "consumer"
            user.onboarding_state = "mode_set"
        elif payload == "mode:business":
            user.current_mode = "business"
            user.onboarding_state = "mode_set"
        else:
            if cid:
                await client.answer_callback(
                    callback_id=cid,
                    notification="Неизвестная кнопка",
                )
            await session.commit()
            return
        await session.commit()
        if cid:
            await client.answer_callback(
                callback_id=cid,
                notification="Сохранено",
            )
        await client.send_message(
            user_id=uid,
            text=(
                "Отлично! Режим сохранён: "
                + ("«для себя»" if user.current_mode == "consumer" else "«для бизнеса»")
                + ". Напишите сообщение — дальше подключим ответы нейросети."
            ),
        )
        return

    if ut == "bot_started":
        uid = extract_bot_started_user_id(update)
        if uid is None:
            logger.warning("bot_started without resolvable user_id: %s", update)
            return
        user = await _get_or_create_user(session, uid)
        await session.commit()
        await client.send_message(
            user_id=uid,
            text="Привет! Это MAX-бот по спецификации MVP. Выберите режим ниже.",
        )
        await _prompt_mode(client, uid)
        return

    logger.debug("MAX update ignored type=%s", ut)
