"""M10: таблицы сырого webhook и идемпотентности (webhook_raw_events, webhook_processed).

Revision ID: 008_m10
Revises: 007_m9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_m10"
down_revision = "007_m9"
branch_labels = None
depends_on = None


def _has_table(bind: sa.engine.Connection, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "webhook_raw_events"):
        op.create_table(
            "webhook_raw_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("body_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_webhook_raw_events_idempotency_key",
            "webhook_raw_events",
            ["idempotency_key"],
        )
    if not _has_table(bind, "webhook_processed"):
        op.create_table(
            "webhook_processed",
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("idempotency_key"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "webhook_processed"):
        op.drop_table("webhook_processed")
    if _has_table(bind, "webhook_raw_events"):
        op.drop_index("ix_webhook_raw_events_idempotency_key", table_name="webhook_raw_events")
        op.drop_table("webhook_raw_events")
