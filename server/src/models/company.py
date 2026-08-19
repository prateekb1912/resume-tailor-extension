from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class Company(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "companies"

    source: Mapped[str] = mapped_column(String(32), index=True)  # JobSource value
    board: Mapped[str] = mapped_column(String(255))  # board slug on that source
    name: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    __table_args__ = (UniqueConstraint("source", "board", name="uq_companies_source_board"),)
