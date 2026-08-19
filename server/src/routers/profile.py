import logging

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from src.config.database import get_db
from src.config.dependencies import get_current_profile
from src.models import Profile
from src.schemas.profile import Preferences, ProfileResponse
from src.services import profile_service

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/", response_model=ProfileResponse, status_code=200)
def get_profile(profile: Profile = Depends(get_current_profile)) -> ProfileResponse:
    return ProfileResponse.model_validate(profile.to_dict())


@router.put("/preferences", response_model=ProfileResponse, status_code=200)
def set_preferences(
    preferences: Preferences,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    updated = profile_service.set_preferences(profile.email, preferences, db)
    return ProfileResponse.model_validate(updated.to_dict())
