import logging

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status

from src.config.database import get_db
from src.schemas.profile import ProfileIn, ProfileResponse
from src.services import profile_service

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/", response_model=ProfileResponse, status_code=200)
def get_profile(payload: ProfileIn, db: Session = Depends(get_db)) -> ProfileResponse:
    profile = profile_service.get_profile(payload.email, db)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile found associated with this email",
        )

    return ProfileResponse.model_validate(profile.to_dict())
