"""CLI: истечение подписок + попытка рекуррентного списания (запуск по cron).

Пример:
  python -m packages.billing.renewal_cli
"""

from __future__ import annotations

import asyncio
import logging
import sys

from apps.bot.max_client import MaxBotClient
from packages.billing.factory import get_billing_service
from packages.billing.max_notices import notice_access_expired
from packages.billing.renewal_job import expire_subscriptions_past_due, run_renewal_charges
from packages.billing.webhook_logic import load_max_user_id
from packages.db.session import create_engine, get_session_factory
from packages.shared.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def _amain() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = get_session_factory(engine)
    billing = get_billing_service(settings)
    expired_users = await expire_subscriptions_past_due(session_factory=factory, billing=billing)
    client = MaxBotClient(settings)
    for uid in expired_users:
        async with factory() as session:
            max_uid = await load_max_user_id(session, uid)
        if max_uid is None or not settings.max_outbound_enabled:
            continue
        ok = await client.send_message(user_id=max_uid, text=notice_access_expired(), fmt="markdown")
        logger.info("m7_event=expiry_notice_sent user_id=%s max_user_id=%s ok=%s", uid, max_uid, ok)
    n = await run_renewal_charges(settings=settings, session_factory=factory)
    logger.info("m7_renewal_cli done renewals_attempted_ok=%s", n)
    await engine.dispose()
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_amain()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
