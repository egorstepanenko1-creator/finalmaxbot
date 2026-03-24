"""M7: рекуррентные подписки — состояния, RebillId, авто-продление.

Revision ID: 005_m7
Revises: 004_m6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_m7"
down_revision = "004_m6"
branch_labels = None
depends_on = None


def _has_column(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "subscriptions", "subscription_state"):
        with op.batch_alter_table("subscriptions") as batch:
            batch.add_column(sa.Column("subscription_state", sa.String(length=32), nullable=True))
            batch.add_column(sa.Column("tbank_rebill_id", sa.String(length=64), nullable=True))
            batch.add_column(sa.Column("tbank_customer_key", sa.String(length=64), nullable=True))
            batch.add_column(sa.Column("tbank_parent_payment_id", sa.String(length=64), nullable=True))
            batch.add_column(
                sa.Column(
                    "auto_renew_enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )
            batch.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))

    # backfill state from legacy status
    op.execute(
        """
        UPDATE subscriptions SET subscription_state = 'active'
        WHERE subscription_state IS NULL AND status = 'active'
        """
    )
    op.execute(
        """
        UPDATE subscriptions SET subscription_state = 'expired'
        WHERE subscription_state IS NULL AND status = 'superseded'
        """
    )
    op.execute(
        """
        UPDATE subscriptions SET subscription_state = 'cancelled'
        WHERE subscription_state IS NULL AND status = 'cancelled'
        """
    )
    op.execute(
        """
        UPDATE subscriptions SET subscription_state = 'expired'
        WHERE subscription_state IS NULL
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "subscriptions", "subscription_state"):
        with op.batch_alter_table("subscriptions") as batch:
            batch.drop_column("cancelled_at")
            batch.drop_column("auto_renew_enabled")
            batch.drop_column("tbank_parent_payment_id")
            batch.drop_column("tbank_customer_key")
            batch.drop_column("tbank_rebill_id")
            batch.drop_column("subscription_state")
