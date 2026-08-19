from typing import Annotated

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from src.config.database import get_db
from src.config.dependencies import get_current_profile
from src.config.settings import settings
from src.models import Profile
from src.schemas.profile import ProfileResponse, TailorResumePayload
from src.services import profile_service

router = APIRouter()


@router.post("/parse", response_model=ProfileResponse)
def parse_resume(
    resume: Annotated[UploadFile, File()],
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    if resume.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF resumes are supported",
        )
    file_bytes = resume.file.read()
    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )
    parsed = profile_service.create_profile_with_resume(profile.email, file_bytes, db)
    return ProfileResponse(data=parsed, name=parsed.name, email=profile.email)


@router.post("/tailor")
def tailor_resume_to_job(
    payload: TailorResumePayload,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    if not payload.job_description or len(payload.job_description) < 100:
        raise HTTPException(
            status_code=status.HTTP_411_LENGTH_REQUIRED,
            detail="Job description not found or too short to tailor resume",
        )
    payload.email = profile.email  # identity comes from the token, not the client
    return profile_service.tailor_resume_to_job(payload, db)
