"""Клавиатуры главного меню (callback payload v1)."""

from __future__ import annotations

from typing import Any

import packages.shared.callbacks as cb


def _row(*buttons: dict[str, Any]) -> list[dict[str, Any]]:
    return list(buttons)


def consumer_main_menu() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Задать вопрос",
                            "payload": cb.CONSUMER_ASK_QUESTION,
                        },
                        {
                            "type": "callback",
                            "text": "Сделать картинку",
                            "payload": cb.CONSUMER_CREATE_IMAGE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Поздравление",
                            "payload": cb.CONSUMER_MAKE_GREETING,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Мои звёзды",
                            "payload": cb.CONSUMER_MY_STARS,
                        },
                        {
                            "type": "callback",
                            "text": "Пригласить друга",
                            "payload": cb.CONSUMER_INVITE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Подписка",
                            "payload": cb.CONSUMER_SUBSCRIPTION,
                        },
                    ),
                ]
            },
        }
    ]


def business_main_menu() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Пост для VK",
                            "payload": cb.BUSINESS_VK_POST,
                        },
                        {
                            "type": "callback",
                            "text": "Сделать картинку",
                            "payload": cb.BUSINESS_CREATE_IMAGE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Мои звёзды",
                            "payload": cb.BUSINESS_MY_STARS,
                        },
                        {
                            "type": "callback",
                            "text": "Пригласить друга",
                            "payload": cb.BUSINESS_INVITE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Подписка",
                            "payload": cb.BUSINESS_SUBSCRIPTION,
                        },
                    ),
                ]
            },
        }
    ]


def mode_selection_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Для себя",
                            "payload": cb.MODE_CONSUMER,
                        },
                        {
                            "type": "callback",
                            "text": "Для бизнеса",
                            "payload": cb.MODE_BUSINESS,
                        },
                    ),
                ]
            },
        }
    ]
