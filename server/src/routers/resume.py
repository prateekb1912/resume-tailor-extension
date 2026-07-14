from typing import Annotated
from sqlalchemy.orm import Session

from fastapi import APIRouter, File, HTTPException, UploadFile, status, Depends

from src.config.database import get_db
from src.config.settings import settings
from src.schemas.profile import ProfileResponse
from src.services import profile_service

router = APIRouter()


@router.post("/parse", response_model=ProfileResponse)
def parse_resume(
    resume: Annotated[UploadFile, File()], db: Session = Depends(get_db)
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
    profile = profile_service.parse_resume(file_bytes, db)
    return ProfileResponse(data=profile)
