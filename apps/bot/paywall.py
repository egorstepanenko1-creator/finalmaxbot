"""Детерминированные тексты и клавиатура paywall (M4)."""

from __future__ import annotations

from typing import Any

import packages.shared.callbacks as cb


def paywall_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": "Оформить подписку",
                            "payload": cb.PAYWALL_SUBSCRIBE,
                        },
                        {
                            "type": "callback",
                            "text": "Пригласить друга",
                            "payload": cb.PAYWALL_INVITE,
                        },
                    ],
                    [
                        {
                            "type": "callback",
                            "text": "Ввести код приглашения",
                            "payload": cb.PAYWALL_ENTER_CODE,
                        },
                    ],
                ]
            },
        }
    ]


def paywall_text_image_quota(*, used: int, limit: int) -> str:
    return (
        f"Сегодня использовано **{used}** из **{limit}** «картиночных» действий "
        "(картинка или поздравление).\n\n"
        "Что можно сделать:\n"
        "• **Оформить подписку** — больше возможностей без водяного знака.\n"
        "• **Пригласить друга** — друг вводит ваш код; после его первой заявки на картинку вам +3★.\n"
        "• **Ввести код приглашения**, если вас пригласили."
    )


def paywall_text_text_quota(*, used: int, limit: int) -> str:
    return (
        f"Достигнут лимит вопросов на сутки (**{used}** / **{limit}**).\n"
        "Оформите подписку или вернитесь завтра."
    )


def paywall_text_vk_not_entitled() -> str:
    return (
        "Посты для VK доступны на тарифе **business_marketer_490**.\n"
        "Нажмите «Оформить подписку» и выберите бизнес-тариф (когда подключим оплату)."
    )


def paywall_text_vk_quota(*, used: int, limit: int) -> str:
    return (
        f"Лимит постов VK в этом месяце: **{used}** / **{limit}**.\n"
        "Оформите продление или подождите следующего месяца."
    )
