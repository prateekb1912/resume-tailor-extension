import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config.enums import TailorStatus
from src.schemas.profile import ProfileData
from src.models.base import Base, TimestampMixin, UUIDMixin


class TailorJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tailor_jobs"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[TailorStatus] = mapped_column(
        SAEnum(TailorStatus, name="tailor_status"), default=TailorStatus.PENDING
    )

    job_title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(500))
    job_url: Mapped[str | None] = mapped_column(String(2000))
    jd_text: Mapped[str] = mapped_column(Text)

    match_score: Mapped[int | None]
    reason: Mapped[str | None] = mapped_column(Text)
    missing_skills: Mapped[str | None] = mapped_column(Text)

    result_data: Mapped[dict[str, ProfileData]] = mapped_column(JSONB)

    error: Mapped[str | None] = mapped_column(Text)
