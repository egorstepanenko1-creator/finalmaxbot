"""M3: все таблицы через metadata.create_all (идемпотентно checkfirst).

Revision ID: 001_m3
Revises:
Create Date: 2026-03-23
"""

from __future__ import annotations

from alembic import op

from packages.db import models  # noqa: F401
from packages.db.base import Base

revision = "001_m3"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
