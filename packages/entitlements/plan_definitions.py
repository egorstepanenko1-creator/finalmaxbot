"""Планы и лимиты M4 — строятся из Settings (config-driven)."""

from __future__ import annotations

from dataclasses import dataclass

from packages.shared.settings import Settings


@dataclass(frozen=True)
class PlanEntitlements:
    plan_code: str
    watermark_on_image: bool
    premium_style_enabled: bool
    # Картинки: либо rolling 24h, либо календарный месяц (см. use_monthly_image_quota)
    max_image_events_rolling_24h: int | None
    max_image_events_per_calendar_month: int | None
    use_monthly_image_quota: bool
    # Текстовые диалоги (ask_question), rolling 24h
    max_text_chats_rolling_24h: int
    # VK посты в месяц (только business_marketer_490)
    max_vk_posts_per_calendar_month: int | None
    vk_flow_enabled: bool


def plan_entitlements_for(plan_code: str, s: Settings) -> PlanEntitlements:
    if plan_code == "consumer_free":
        return PlanEntitlements(
            plan_code=plan_code,
            watermark_on_image=True,
            premium_style_enabled=False,
            max_image_events_rolling_24h=s.m4_consumer_free_images_per_rolling_24h,
            max_image_events_per_calendar_month=None,
            use_monthly_image_quota=False,
            max_text_chats_rolling_24h=s.m4_consumer_free_text_chats_per_rolling_24h,
            max_vk_posts_per_calendar_month=None,
            vk_flow_enabled=False,
        )
    if plan_code == "consumer_plus_290":
        return PlanEntitlements(
            plan_code=plan_code,
            watermark_on_image=False,
            premium_style_enabled=True,
            max_image_events_rolling_24h=None,
            max_image_events_per_calendar_month=s.m4_consumer_plus_max_images_per_month,
            use_monthly_image_quota=True,
            max_text_chats_rolling_24h=s.m4_consumer_plus_text_chats_per_rolling_24h,
            max_vk_posts_per_calendar_month=None,
            vk_flow_enabled=False,
        )
    if plan_code == "business_marketer_490":
        return PlanEntitlements(
            plan_code=plan_code,
            watermark_on_image=False,
            premium_style_enabled=True,
            max_image_events_rolling_24h=None,
            max_image_events_per_calendar_month=s.m4_business_marketer_max_images_per_month,
            use_monthly_image_quota=True,
            max_text_chats_rolling_24h=s.m4_business_marketer_text_chats_per_rolling_24h,
            max_vk_posts_per_calendar_month=s.m4_business_marketer_max_vk_posts_per_month,
            vk_flow_enabled=True,
        )
    if plan_code == "business_free":
        return PlanEntitlements(
            plan_code=plan_code,
            watermark_on_image=True,
            premium_style_enabled=False,
            max_image_events_rolling_24h=s.m4_business_free_images_per_rolling_24h,
            max_image_events_per_calendar_month=None,
            use_monthly_image_quota=False,
            max_text_chats_rolling_24h=s.m4_business_free_text_chats_per_rolling_24h,
            max_vk_posts_per_calendar_month=None,
            vk_flow_enabled=False,
        )
    return plan_entitlements_for("consumer_free", s)
