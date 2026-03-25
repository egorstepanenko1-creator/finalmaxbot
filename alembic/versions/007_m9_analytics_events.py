"""M9: analytics_events для продуктовой аналитики.

Revision ID: 007_m9
Revises: 006_m8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_m9"
down_revision = "006_m8"
branch_labels = None
depends_on = None


def _has_table(bind: sa.engine.Connection, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "analytics_events"):
        return
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_name", "analytics_events", ["name"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "analytics_events"):
        return
    op.drop_index("ix_analytics_events_name", table_name="analytics_events")
    op.drop_index("ix_analytics_events_user_id", table_name="analytics_events")
    op.drop_table("analytics_events")
