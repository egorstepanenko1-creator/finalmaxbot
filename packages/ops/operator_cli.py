"""CLI: сводка по max_user_id (тот же payload, что у GET /internal/launch/user, без HTTP).

Пример:
  python -m packages.ops.operator_cli 123456789
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from packages.db.session import create_engine, get_session_factory
from packages.ops.operator_snapshot import build_launch_operator_snapshot
from packages.shared.settings import get_settings


async def _run(max_user_id: int) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    factory = get_session_factory(engine)
    async with factory() as session:
        snap = await build_launch_operator_snapshot(
            session, settings=settings, max_user_id=max_user_id
        )
    await engine.dispose()
    print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    return 0 if snap.get("error") != "user_not_found" else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Операторская сводка по max_user_id")
    p.add_argument("max_user_id", type=int)
    args = p.parse_args()
    try:
        raise SystemExit(asyncio.run(_run(args.max_user_id)))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
