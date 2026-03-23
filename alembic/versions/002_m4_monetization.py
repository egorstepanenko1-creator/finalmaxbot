"""M4: рефералы, watermark на job, FK referred_by.

Revision ID: 002_m4
Revises: 001_m3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_m4"
down_revision = "001_m3"
branch_labels = None
depends_on = None


def _has_column(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "users", "referral_code"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("referred_by_user_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("referral_code", sa.String(length=16), nullable=True))
        op.create_index("ix_users_referred_by_user_id", "users", ["referred_by_user_id"])
        op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])
        op.create_foreign_key(
            "fk_users_referred_by_user_id",
            "users",
            "users",
            ["referred_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if not _has_column(bind, "generation_jobs", "watermark_required"):
        with op.batch_alter_table("generation_jobs") as batch:
            batch.add_column(
                sa.Column(
                    "watermark_required",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("1"),
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "generation_jobs", "watermark_required"):
        with op.batch_alter_table("generation_jobs") as batch:
            batch.drop_column("watermark_required")

    if _has_column(bind, "users", "referral_code"):
        op.drop_constraint("fk_users_referred_by_user_id", "users", type_="foreignkey")
        op.drop_constraint("uq_users_referral_code", "users", type_="unique")
        op.drop_index("ix_users_referred_by_user_id", table_name="users")
        with op.batch_alter_table("users") as batch:
            batch.drop_column("referral_code")
            batch.drop_column("referred_by_user_id")
