from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from src.config.settings import settings


def hash_password(plain: str) -> str:
    encoded_pw = plain.encode("utf-8")
    return bcrypt.hashpw(encoded_pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    encoded_pw = plain.encode("utf-8")
    encoded_hash = hashed.encode("utf-8")

    return bcrypt.checkpw(encoded_pw, encoded_hash)


def create_access_token(subject: str, exp_mins: int | None = None) -> str:
    minutes = exp_mins if exp_mins is not None else settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, key=settings.jwt_secret, algorithms=[settings.jwt_algorithm])
