"""Детерминированные тексты и клавиатура paywall (M4/M6)."""

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
                            "text": "Для себя — 290 ₽",
                            "payload": cb.PAYWALL_SUBSCRIBE_CONSUMER_PLUS,
                        },
                        {
                            "type": "callback",
                            "text": "Бизнес — 490 ₽",
                            "payload": cb.PAYWALL_SUBSCRIBE_BUSINESS_PLAN,
                        },
                    ],
                    [
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
        "• **Оплатить подписку** — кнопки «Для себя» или «Бизнес» откроют безопасную оплату Т-Банка.\n"
        "• **Пригласить друга** — после его первой картинки вам +3★.\n"
        "• **Ввести код приглашения**, если вас пригласили."
    )


def paywall_text_text_quota(*, used: int, limit: int) -> str:
    return (
        f"Достигнут лимит вопросов на сутки (**{used}** / **{limit}**).\n"
        "Оформите подписку кнопкой ниже или вернитесь завтра."
    )


def paywall_text_vk_not_entitled() -> str:
    return (
        "Посты для VK доступны на тарифе **бизнес — 490 ₽**.\n"
        "Нажмите кнопку **«Бизнес — 490 ₽»** ниже — откроется оплата в Т-Банке."
    )


def paywall_text_vk_quota(*, used: int, limit: int) -> str:
    return (
        f"Лимит постов VK в этом месяце: **{used}** / **{limit}**.\n"
        "Продлите подписку или дождитесь следующего месяца."
    )
