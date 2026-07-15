import io
import logging

from sqlalchemy.orm import Session

from fastapi import HTTPException, status
from pypdf import PdfReader

from src.models import Profile, TailorJob
from src.schemas.profile import ProfileData, TailorResumePayload, TailoredResumeResult
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


def create_profile_with_resume(email: str, file_bytes: bytes, db: Session) -> ProfileData:
    text = _extract_pdf_text(file_bytes)
    raw = llm.extract_resume(text)
    profile_data = ProfileData.model_validate(raw)

    profile = get_profile(email, db)

    if not profile:
        profile = Profile(email=profile_data.email)
        db.add(profile)

    profile.data = profile_data.model_dump()
    profile.name = profile_data.name

    db.commit()
    return profile_data


def get_profile(email: str, db: Session) -> Profile | None:
    profile = db.query(Profile).filter(Profile.email == email).one_or_none()

    return profile


def tailor_resume_to_job(payload: TailorResumePayload, db: Session) -> TailoredResumeResult:
    profile = get_profile(payload.email, db)
    if not profile:
        raise NameError(f"No profile found with the associated email: {payload.email}")

    profile_data = ProfileData.model_validate(profile.data)

    tailored_resume = llm.tailor_resume(
        payload.company, payload.job_title, payload.job_description, profile_data
    )

    tailor_job = TailorJob(
        profile_id=profile.id,
        job_title=payload.job_title,
        job_url=payload.job_url,
        company=payload.company,
        jd_text=payload.job_description,
        result_data=tailored_resume.profile.model_dump(),
        match_score=tailored_resume.fit.match_score,
        reason=tailored_resume.fit.reason,
        missing_skills=tailored_resume.fit.missing_skills,
    )
    db.add(tailor_job)
    db.commit()

    return tailored_resume
