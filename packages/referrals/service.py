"""Рефералы: код приглашения, привязка, награда +3★ после первой «картинки»."""

from __future__ import annotations

import secrets
import string
from typing import Any

from sqlalchemy import select

from packages.db.models import Referral, User
from packages.stars.service import StarsLedgerService


class ReferralService:
    def __init__(self, stars: StarsLedgerService) -> None:
        self._stars = stars

    async def ensure_referral_code(self, session: Any, user: User) -> str:
        if user.referral_code:
            return user.referral_code
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = "R-" + "".join(secrets.choice(alphabet) for _ in range(8))
            r = await session.execute(select(User.id).where(User.referral_code == code))
            if r.scalar_one_or_none() is None:
                user.referral_code = code
                await session.flush()
                return code
        raise RuntimeError("could not allocate referral code")

    async def attach_by_code(self, session: Any, invitee: User, raw_code: str) -> tuple[bool, str]:
        code = raw_code.strip().upper()
        if not code.startswith("R-"):
            code = "R-" + code.removeprefix("R-").strip()
        if invitee.referred_by_user_id is not None:
            return False, "already_attached"
        r = await session.execute(select(User).where(User.referral_code == code))
        inviter = r.scalar_one_or_none()
        if inviter is None:
            return False, "unknown_code"
        if inviter.id == invitee.id:
            return False, "self_referral"
        ex = await session.execute(
            select(Referral).where(Referral.invitee_user_id == invitee.id)
        )
        if ex.scalar_one_or_none():
            return False, "invitee_already_has_referral"
        session.add(
            Referral(
                inviter_user_id=inviter.id,
                invitee_user_id=invitee.id,
                status="pending",
            )
        )
        invitee.referred_by_user_id = inviter.id
        await session.flush()
        return True, "ok"

    async def try_reward_on_first_image_flow(self, session: Any, invitee: User) -> None:
        """После первого consumer/business image-события или поздравления (квота картинки)."""
        r = await session.execute(
            select(Referral).where(
                Referral.invitee_user_id == invitee.id,
                Referral.status == "pending",
            )
        )
        ref = r.scalar_one_or_none()
        if ref is None:
            return
        if ref.inviter_user_id == invitee.id:
            return
        from datetime import UTC, datetime

        ref.status = "rewarded"
        ref.reward_granted_at = datetime.now(UTC)
        await self._stars.credit(
            session,
            user_id=ref.inviter_user_id,
            delta=3,
            reason="referral_first_image",
            ref_type="referral",
            ref_id=str(ref.id),
        )
        await session.flush()
