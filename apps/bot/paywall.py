"""Детерминированные тексты и клавиатура paywall (M4/M6)."""

from __future__ import annotations

from typing import Any

import packages.shared.callbacks as cb
from packages.shared import user_copy_ru as ru


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
                            "text": "Пригласить друга 👥",
                            "payload": cb.PAYWALL_INVITE,
                        },
                    ],
                    [
                        {
                            "type": "callback",
                            "text": "У меня есть код",
                            "payload": cb.PAYWALL_ENTER_CODE,
                        },
                    ],
                ]
            },
        }
    ]


def paywall_text_image_quota(*, used: int, limit: int) -> str:
    return ru.PAYWALL_IMAGE_QUOTA.format(used=used, limit=limit)


def paywall_text_text_quota(*, used: int, limit: int) -> str:
    return ru.PAYWALL_TEXT_QUOTA.format(used=used, limit=limit)


def paywall_text_vk_not_entitled() -> str:
    return ru.PAYWALL_VK_NOT_ENTITLED


def paywall_text_vk_quota(*, used: int, limit: int) -> str:
    return ru.PAYWALL_VK_QUOTA.format(used=used, limit=limit)
