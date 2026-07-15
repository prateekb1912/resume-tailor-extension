import io
import logging

from sqlalchemy.orm import Session

from fastapi import HTTPException, status
from pypdf import PdfReader

from src.models.profile import Profile
from src.schemas.profile import ProfileData, TailorResumePayload
from src.services import llm

logger = logging.getLogger(__name__)


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read PDF")
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable text in PDF (is it a scanned image?)",
        )
    return text


def create_profile_with_resume(file_bytes: bytes, db: Session) -> ProfileData:
    text = _extract_pdf_text(file_bytes)
    raw = llm.extract_resume(text)
    profile_data = ProfileData.model_validate(raw)
    profile = Profile(
        data=profile_data.model_dump(), name=profile_data.name, email=profile_data.email
    )

    db.add(profile)
    db.commit()
    return profile_data


def get_profile(email: str, db: Session) -> Profile:
    profile = db.query(Profile).filter(Profile.email == email).one_or_none()

    if profile is None:
        raise NameError(f"No profile found with the associated email: {email}")

    return profile


def tailor_resume_to_job(payload: TailorResumePayload, db: Session):
    try:
        profile = get_profile(payload.email, db)
    except Exception as _:
        raise NameError(f"No profile found with the associated email: {payload.email}")

    profile_data = ProfileData.model_validate(profile.data)

    return llm.tailor_resume(
        payload.company, payload.job_title, payload.job_description, profile_data
    )
