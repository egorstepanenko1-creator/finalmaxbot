"""HTTP endpoint для уведомлений Т-Банка (Acquiring)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.bot.max_client import MaxBotClient
from packages.billing.factory import get_billing_service
from packages.billing.tbank_service import TBankBillingService
from packages.billing.webhook_logic import load_max_user_id, process_tbank_notification_json
from packages.shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


def _activation_message(plan_code: str) -> str:
    if plan_code == "business_marketer_490":
        return (
            "**Оплата прошла успешно.**\n\n"
            "Ваш тариф **бизнес-маркетолог** активен: больше картинок, посты для VK без лишних ограничений, "
            "без водяного знака на картинках.\n\n"
            "Выберите действие в меню — начнём с задачи для вашего бизнеса."
        )
    return (
        "**Оплата прошла успешно.**\n\n"
        "Подписка **для себя** активна: больше «картиночных» действий и вопросов, без водяного знака.\n\n"
        "Выберите в меню, что сделаем дальше."
    )


async def _send_activation_notice(
    *,
    settings: Settings,
    session_factory: Any,
    internal_user_id: int,
    plan_code: str,
) -> None:
    async with session_factory() as session:
        max_uid = await load_max_user_id(session, internal_user_id)
    if max_uid is None:
        logger.warning("m6_event=activation_notice_skipped user_id=%s (no max_user_id)", internal_user_id)
        return
    client = MaxBotClient(settings)
    text = _activation_message(plan_code)
    ok = await client.send_message(user_id=max_uid, text=text, fmt="markdown")
    logger.info(
        "m6_event=activation_notice_sent user_id=%s max_user_id=%s ok=%s plan=%s",
        internal_user_id,
        max_uid,
        ok,
        plan_code,
    )


@router.post("/webhooks/tbank/notification")
async def tbank_notification(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    if not settings.tbank_terminal_key or not settings.tbank_password:
        raise HTTPException(status_code=404, detail="tbank not configured")
    billing = get_billing_service(settings)
    if not isinstance(billing, TBankBillingService):
        raise HTTPException(status_code=503, detail="billing adapter mismatch")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="expected json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected object")

    correlation = str(body.get("OrderId") or body.get("PaymentId") or "")
    logger.info("m6_event=billing_callback_received correlation_id=%s", correlation)

    factory = request.app.state.session_factory
    async with factory() as session:
        ok, reason, uid = await process_tbank_notification_json(
            session=session,
            body=body,
            billing=billing,
            verify_token=billing.verify_notification_token,
        )
    if reason == "activated" and uid is not None:
        plan_code = ""
        data_raw = body.get("DATA")
        if isinstance(data_raw, str):
            try:
                d = json.loads(data_raw)
                if isinstance(d, dict):
                    plan_code = str(d.get("plan_code") or "")
            except json.JSONDecodeError:
                plan_code = ""
        elif isinstance(data_raw, dict):
            plan_code = str(data_raw.get("plan_code") or "")
        if plan_code and plan_code != "stars_topup_99":
            asyncio.create_task(
                _send_activation_notice(
                    settings=settings,
                    session_factory=factory,
                    internal_user_id=uid,
                    plan_code=plan_code,
                )
            )
    _ = ok
    return JSONResponse(content={"OK": True})
