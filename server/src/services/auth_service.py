from sqlalchemy.orm import Session

from fastapi import HTTPException, status

from src.config.security import create_access_token, hash_password, verify_password
from src.models import Profile
from src.services import profile_service


def register(email: str, password: str, db: Session) -> str:
    existing = profile_service.get_profile(email, db)
    if existing and existing.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # A profile may already exist from a resume upload made before signup — claim it.
    profile = existing or Profile(email=email, data={})
    profile.password_hash = hash_password(password)
    if existing is None:
        db.add(profile)
    db.commit()
    return create_access_token(subject=email)


def authenticate(email: str, password: str, db: Session) -> str:
    profile = profile_service.get_profile(email, db)
    if not profile or not profile.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not verify_password(password, profile.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return create_access_token(subject=email)
