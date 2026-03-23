"""
Версионированные callback payload для MAX inline_keyboard.
Формат: v1|<область>|... — при смене контракта поднимаем префикс (v2|...).
"""

from __future__ import annotations

VER = "v1"
SEP = "|"


def join_parts(*parts: str) -> str:
    return SEP.join((VER,) + parts)


# Режим (совместимость: старые mode:consumer всё ещё обрабатываются в роутере)
MODE_CONSUMER = join_parts("mode", "consumer")
MODE_BUSINESS = join_parts("mode", "business")

# Consumer main
CONSUMER_ASK_QUESTION = join_parts("consumer", "ask_question")
CONSUMER_CREATE_IMAGE = join_parts("consumer", "create_image")
CONSUMER_MAKE_GREETING = join_parts("consumer", "make_greeting")
CONSUMER_MY_STARS = join_parts("consumer", "my_stars")
CONSUMER_INVITE = join_parts("consumer", "invite_friend")
CONSUMER_SUBSCRIPTION = join_parts("consumer", "subscription")

# Business main
BUSINESS_VK_POST = join_parts("business", "create_vk_post")
BUSINESS_CREATE_IMAGE = join_parts("business", "create_image")
BUSINESS_MY_STARS = join_parts("business", "my_stars")
BUSINESS_INVITE = join_parts("business", "invite_friend")
BUSINESS_SUBSCRIPTION = join_parts("business", "subscription")

# Paywall / реферал
PAYWALL_SUBSCRIBE = join_parts("paywall", "subscribe")
PAYWALL_SUBSCRIBE_CONSUMER_PLUS = join_parts("paywall", "subscribe_consumer_plus")
PAYWALL_SUBSCRIBE_BUSINESS_PLAN = join_parts("paywall", "subscribe_business")
PAYWALL_INVITE = join_parts("paywall", "invite")
PAYWALL_ENTER_CODE = join_parts("paywall", "enter_code")

CONSUMER_ENTER_REFERRAL = join_parts("consumer", "enter_referral_code")
BUSINESS_ENTER_REFERRAL = join_parts("business", "enter_referral_code")


def parse_payload(raw: str | None) -> tuple[str, list[str]]:
    """Возвращает (версия или 'legacy', сегменты после версии)."""
    if not raw:
        return "empty", []
    if raw.startswith("mode:"):
        return "legacy", [raw]
    if SEP not in raw:
        return "legacy", [raw]
    parts = raw.split(SEP)
    version = parts[0]
    rest = parts[1:]
    return version, rest


def is_v1_consumer_action(segments: list[str], action: str) -> bool:
    return segments == ["consumer", action]


def is_v1_business_action(segments: list[str], action: str) -> bool:
    return segments == ["business", action]


def is_v1_mode(segments: list[str], mode: str) -> bool:
    return segments == ["mode", mode]


def is_v1_paywall_action(segments: list[str], action: str) -> bool:
    return segments == ["paywall", action]


def is_paywall_subscribe_variant(segments: list[str]) -> bool:
    return segments in (
        ["paywall", "subscribe"],
        ["paywall", "subscribe_consumer_plus"],
        ["paywall", "subscribe_business"],
    )
