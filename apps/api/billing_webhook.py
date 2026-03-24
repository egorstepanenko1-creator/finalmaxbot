"""HTTP endpoint для уведомлений Т-Банка (Acquiring)."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.bot.max_client import MaxBotClient
from packages.billing.factory import get_billing_service
from packages.billing.max_notices import (
    notice_renewal_failed,
    notice_subscription_activated,
    notice_subscription_renewed,
)
from packages.billing.tbank_service import TBankBillingService
from packages.billing.webhook_logic import load_max_user_id, process_tbank_notification_json
from packages.shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


async def _send_max_notice(
    *,
    settings: Settings,
    session_factory: Any,
    internal_user_id: int,
    text: str,
    log_event: str,
) -> None:
    async with session_factory() as session:
        max_uid = await load_max_user_id(session, internal_user_id)
    if max_uid is None:
        logger.warning("%s user_id=%s (no max_user_id)", log_event, internal_user_id)
        return
    client = MaxBotClient(settings)
    ok = await client.send_message(user_id=max_uid, text=text, fmt="markdown")
    logger.info(
        "%s user_id=%s max_user_id=%s ok=%s",
        log_event,
        internal_user_id,
        max_uid,
        ok,
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
    logger.info("m7_event=billing_callback_received correlation_id=%s", correlation)

    factory = request.app.state.session_factory
    async with factory() as session:
        res = await process_tbank_notification_json(
            session=session,
            body=body,
            billing=billing,
            verify_token=billing.verify_notification_token,
        )

    if res.user_id is None:
        return JSONResponse(content={"OK": True})

    if res.max_notice == "activated_initial" and res.plan_code:
        asyncio.create_task(
            _send_max_notice(
                settings=settings,
                session_factory=factory,
                internal_user_id=res.user_id,
                text=notice_subscription_activated(plan_code=res.plan_code),
                log_event="m7_event=activation_notice_sent",
            )
        )
    elif res.max_notice == "subscription_renewed" and res.plan_code:
        asyncio.create_task(
            _send_max_notice(
                settings=settings,
                session_factory=factory,
                internal_user_id=res.user_id,
                text=notice_subscription_renewed(plan_code=res.plan_code),
                log_event="m7_event=renewal_notice_sent",
            )
        )
    elif res.max_notice == "renewal_failed":
        asyncio.create_task(
            _send_max_notice(
                settings=settings,
                session_factory=factory,
                internal_user_id=res.user_id,
                text=notice_renewal_failed(),
                log_event="m7_event=renewal_failed_notice_sent",
            )
        )

    return JSONResponse(content={"OK": True})
