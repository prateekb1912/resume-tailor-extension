from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import String

from src.models.base import Base, TimestampMixin, UUIDMixin


class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    def to_dict(self):
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}
