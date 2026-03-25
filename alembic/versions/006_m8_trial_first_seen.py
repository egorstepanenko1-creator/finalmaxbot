"""M8: first_seen_at для онбординг-триала.

Revision ID: 006_m8
Revises: 005_m7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_m8"
down_revision = "005_m7"
branch_labels = None
depends_on = None


def _has_column(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "users", "first_seen_at"):
        return
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE users SET first_seen_at = created_at WHERE first_seen_at IS NULL"))
    # SQLite: оставляем nullable=False через batch — для старых строк уже заполнено
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "first_seen_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "users", "first_seen_at"):
        return
    with op.batch_alter_table("users") as batch:
        batch.drop_column("first_seen_at")
