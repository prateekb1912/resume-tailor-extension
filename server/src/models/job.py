from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class Job(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "jobs"

    source: Mapped[str] = mapped_column(String(32), index=True)  # JobSource value
    external_id: Mapped[str] = mapped_column(String(512))
    dedup_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(512))
    # boards can list many cities in one field — unbounded so it never truncates
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2000))
    description: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Application-tracker status for the Kanban board (single-user MVP; move to job_matches
    # once there are real accounts).
    status: Mapped[str] = mapped_column(String(32), default="new", server_default="new", index=True)
