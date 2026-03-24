"""Клавиатуры главного меню (callback payload v1)."""

from __future__ import annotations

from typing import Any

import packages.shared.callbacks as cb
from packages.content.templates_ru import BUSINESS_TEMPLATES, CONSUMER_TEMPLATES


def _row(*buttons: dict[str, Any]) -> list[dict[str, Any]]:
    return list(buttons)


def consumer_quick_start_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Задать вопрос 💬",
                            "payload": cb.CONSUMER_ASK_QUESTION,
                        },
                        {
                            "type": "callback",
                            "text": "Сделать картинку 🎨",
                            "payload": cb.CONSUMER_CREATE_IMAGE,
                        },
                        {
                            "type": "callback",
                            "text": "Сделать поздравление 🎁",
                            "payload": cb.CONSUMER_MAKE_GREETING,
                        },
                    ),
                ]
            },
        }
    ]


def business_quick_start_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Пост VK",
                            "payload": cb.BUSINESS_VK_POST,
                        },
                        {
                            "type": "callback",
                            "text": "Картинка",
                            "payload": cb.BUSINESS_CREATE_IMAGE,
                        },
                    ),
                ]
            },
        }
    ]


def consumer_templates_keyboard() -> list[dict[str, Any]]:
    buttons: list[list[dict[str, Any]]] = []
    row: list[dict[str, Any]] = []
    for t in CONSUMER_TEMPLATES:
        row.append(
            {
                "type": "callback",
                "text": t.button_label[:35],
                "payload": cb.template_payload("consumer", t.slug),
            }
        )
        if len(row) == 2:
            buttons.append(_row(*row))
            row = []
    if row:
        buttons.append(_row(*row))
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def business_templates_keyboard() -> list[dict[str, Any]]:
    buttons: list[list[dict[str, Any]]] = []
    row = []
    for t in BUSINESS_TEMPLATES:
        row.append(
            {
                "type": "callback",
                "text": t.button_label[:35],
                "payload": cb.template_payload("business", t.slug),
            }
        )
        if len(row) == 2:
            buttons.append(_row(*row))
            row = []
    if row:
        buttons.append(_row(*row))
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def consumer_main_menu() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Задать вопрос 💬",
                            "payload": cb.CONSUMER_ASK_QUESTION,
                        },
                        {
                            "type": "callback",
                            "text": "Сделать картинку 🎨",
                            "payload": cb.CONSUMER_CREATE_IMAGE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Сделать поздравление 🎁",
                            "payload": cb.CONSUMER_MAKE_GREETING,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Шаблоны",
                            "payload": cb.CONSUMER_TEMPLATES_MENU,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Мои звёзды ⭐",
                            "payload": cb.CONSUMER_MY_STARS,
                        },
                        {
                            "type": "callback",
                            "text": "Пригласить друга 👥",
                            "payload": cb.CONSUMER_INVITE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Подписка 💳",
                            "payload": cb.CONSUMER_SUBSCRIPTION,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "У меня есть код",
                            "payload": cb.CONSUMER_ENTER_REFERRAL,
                        },
                    ),
                ]
            },
        }
    ]


def consumer_subscription_keyboard() -> list[dict[str, Any]]:
    """Экран подписки / оплаты: отмена автопродления не в главном меню."""
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Отменить автопродление",
                            "payload": cb.CONSUMER_CANCEL_AUTORENEW,
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
                            "text": "Шаблоны постов",
                            "payload": cb.BUSINESS_TEMPLATES_MENU,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Мои звёзды ⭐",
                            "payload": cb.BUSINESS_MY_STARS,
                        },
                        {
                            "type": "callback",
                            "text": "Пригласить друга 👥",
                            "payload": cb.BUSINESS_INVITE,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "Подписка 💳",
                            "payload": cb.BUSINESS_SUBSCRIPTION,
                        },
                    ),
                    _row(
                        {
                            "type": "callback",
                            "text": "У меня есть код",
                            "payload": cb.BUSINESS_ENTER_REFERRAL,
                        },
                    ),
                ]
            },
        }
    ]


def business_subscription_keyboard() -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    _row(
                        {
                            "type": "callback",
                            "text": "Отменить автопродление",
                            "payload": cb.BUSINESS_CANCEL_AUTORENEW,
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
                            "text": "Для меня",
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
