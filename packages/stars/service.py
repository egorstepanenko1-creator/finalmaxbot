"""Звёзды: баланс = SUM(delta); balance_after — снимок на каждой строке."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from packages.db.models import StarLedgerEntry


class StarsLedgerService:
    async def balance_sum(self, session: Any, user_id: int) -> int:
        r = await session.execute(
            select(func.coalesce(func.sum(StarLedgerEntry.delta), 0)).where(
                StarLedgerEntry.user_id == user_id
            )
        )
        return int(r.scalar() or 0)

    async def credit(
        self,
        session: Any,
        *,
        user_id: int,
        delta: int,
        reason: str,
        ref_type: str | None,
        ref_id: str | None,
    ) -> StarLedgerEntry:
        if delta <= 0:
            raise ValueError("credit expects delta > 0")
        bal = await self.balance_sum(session, user_id) + delta
        row = StarLedgerEntry(
            user_id=user_id,
            delta=delta,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            balance_after=bal,
        )
        session.add(row)
        await session.flush()
        return row

    async def debit(
        self,
        session: Any,
        *,
        user_id: int,
        delta: int,
        reason: str,
        ref_type: str | None,
        ref_id: str | None,
    ) -> StarLedgerEntry:
        if delta <= 0:
            raise ValueError("debit expects delta > 0")
        bal = await self.balance_sum(session, user_id) - delta
        row = StarLedgerEntry(
            user_id=user_id,
            delta=-delta,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            balance_after=bal,
        )
        session.add(row)
        await session.flush()
        return row
