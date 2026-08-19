import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class JobMatch(Base, UUIDMixin, TimestampMixin):
    """Per-profile screening result for a job. Same job scores differently per user's
    resume + preferences, so this is keyed on (profile_id, job_id) rather than on jobs."""

    __tablename__ = "job_matches"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    match_score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_skills: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )

    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_job_matches_profile_job"),)
