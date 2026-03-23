"""M5: stored_files, расширение generation_jobs, миграция статусов.

Revision ID: 003_m5
Revises: 002_m4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_m5"
down_revision = "002_m4"
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

    if not _has_column(bind, "generation_jobs", "correlation_id"):
        with op.batch_alter_table("generation_jobs") as batch:
            batch.add_column(sa.Column("correlation_id", sa.String(length=64), nullable=True))
            batch.add_column(sa.Column("context_kind", sa.String(length=64), nullable=True))
            batch.add_column(sa.Column("meta", sa.JSON(), nullable=True))
            batch.add_column(sa.Column("error_message", sa.Text(), nullable=True))
            batch.add_column(sa.Column("provider_meta", sa.JSON(), nullable=True))
            batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_generation_jobs_correlation_id", "generation_jobs", ["correlation_id"])
        op.create_index("ix_generation_jobs_context_kind", "generation_jobs", ["context_kind"])

    if not _has_table(bind, "stored_files"):
        op.create_table(
            "stored_files",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("generation_job_id", sa.Integer(), nullable=False),
            sa.Column("storage_backend", sa.String(length=32), nullable=False, server_default="local"),
            sa.Column("storage_key", sa.String(length=512), nullable=False),
            sa.Column("mime_type", sa.String(length=64), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256_hex", sa.String(length=64), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["generation_job_id"], ["generation_jobs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("generation_job_id", name="uq_stored_files_generation_job_id"),
        )

    op.execute(sa.text("UPDATE generation_jobs SET status = 'succeeded' WHERE status = 'placeholder'"))
    op.execute(
        sa.text(
            "UPDATE generation_jobs SET correlation_id = 'migrated-' || CAST(id AS TEXT) "
            "WHERE correlation_id IS NULL"
        )
    )
    op.execute(sa.text("UPDATE generation_jobs SET updated_at = created_at WHERE updated_at IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "stored_files"):
        op.drop_table("stored_files")
    if _has_column(bind, "generation_jobs", "correlation_id"):
        op.drop_index("ix_generation_jobs_context_kind", table_name="generation_jobs")
        op.drop_index("ix_generation_jobs_correlation_id", table_name="generation_jobs")
        with op.batch_alter_table("generation_jobs") as batch:
            batch.drop_column("updated_at")
            batch.drop_column("provider_meta")
            batch.drop_column("error_message")
            batch.drop_column("meta")
            batch.drop_column("context_kind")
            batch.drop_column("correlation_id")
