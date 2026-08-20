from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import String

from src.models.base import Base, TimestampMixin, UUIDMixin


class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_linkedin_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    def to_dict(self):
        # never expose password_hash
        return {
            c.key: getattr(self, c.key)
            for c in self.__mapper__.column_attrs
            if c.key != "password_hash"
        }
