"""M6: billing_events, expires_at у subscriptions.

Revision ID: 004_m6
Revises: 003_m5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_m6"
down_revision = "003_m5"
branch_labels = None
depends_on = None


def _has_column(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_table(bind: sa.engine.Connection, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "subscriptions", "expires_at"):
        with op.batch_alter_table("subscriptions") as batch:
            batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    if not _has_table(bind, "billing_events"):
        op.create_table(
            "billing_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="tbank"),
            sa.Column("event_type", sa.String(length=64), nullable=False, server_default="notification"),
            sa.Column("outcome", sa.String(length=32), nullable=False, server_default="received"),
            sa.Column("order_id", sa.String(length=128), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("plan_code", sa.String(length=32), nullable=True),
            sa.Column("payload_safe", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_billing_events_idempotency_key"),
        )
        op.create_index("ix_billing_events_order_id", "billing_events", ["order_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "billing_events"):
        op.drop_index("ix_billing_events_order_id", table_name="billing_events")
        op.drop_table("billing_events")
    if _has_column(bind, "subscriptions", "expires_at"):
        with op.batch_alter_table("subscriptions") as batch:
            batch.drop_column("expires_at")
