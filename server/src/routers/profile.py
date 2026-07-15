import logging

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from src.config.database import get_db
from src.schemas.profile import ProfileData, ProfileIn, ProfileResponse
from src.services import profile_service

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/", response_model=ProfileResponse, status_code=200)
def get_profile(payload: ProfileIn, db: Session = Depends(get_db)) -> ProfileResponse:
    profile = profile_service.get_profile(payload.email, db)

    return ProfileResponse(data=ProfileData.model_validate(profile.data))
