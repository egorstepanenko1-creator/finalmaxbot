from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from packages.db.base import Base


class User(Base):
    """Сущность из implementation pack: max_user_id, current_mode, onboarding_state."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    max_user_id: Mapped[int] = mapped_column(BigInteger(), unique=True, index=True)
    current_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    onboarding_state: Mapped[str] = mapped_column(String(64), default="new")
