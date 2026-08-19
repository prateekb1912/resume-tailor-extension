import jwt
from sqlalchemy.orm import Session

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src.config.database import get_db
from src.config.security import decode_access_token
from src.models import Profile
from src.services import profile_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_profile(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Profile:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise _credentials_exc

    email = payload.get("sub")
    if not email:
        raise _credentials_exc

    profile = profile_service.get_profile(email, db)
    if not profile:
        raise _credentials_exc
    return profile
