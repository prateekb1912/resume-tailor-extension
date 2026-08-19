import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from src.config.enums import ApplicationStatus


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    title: str
    company: str
    location: str | None = None
    url: str
    status: str
    posted_at: datetime | None = None
    # populated only for the per-user matched feed (?email=)
    match_score: int | None = None
    reason: str | None = None


class JobStatusUpdate(BaseModel):
    status: ApplicationStatus


class MatchRequest(BaseModel):
    email: EmailStr
