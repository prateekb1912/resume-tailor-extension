from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import String

from src.models.base import Base, TimestampMixin, UUIDMixin

from src.schemas.profile import ProfileData


class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    data: Mapped[dict[str, ProfileData]] = mapped_column(JSONB)
    name: Mapped[str] = mapped_column(String(32), nullable=True)
    email: Mapped[str] = mapped_column(String(32), nullable=True)
