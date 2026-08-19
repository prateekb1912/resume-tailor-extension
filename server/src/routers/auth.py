from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, status

from src.config.database import get_db
from src.config.dependencies import get_current_profile
from src.models import Profile
from src.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from src.schemas.profile import ProfileResponse
from src.services import auth_service

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token = auth_service.register(payload.email, payload.password, db)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token = auth_service.authenticate(payload.email, payload.password, db)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=ProfileResponse)
def me(profile: Profile = Depends(get_current_profile)) -> ProfileResponse:
    return ProfileResponse.model_validate(profile.to_dict())
