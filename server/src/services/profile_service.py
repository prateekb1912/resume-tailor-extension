import io
import logging

from sqlalchemy.orm import Session

from fastapi import HTTPException, status
from pypdf import PdfReader

from src.models import Profile, TailorJob
from src.schemas.profile import (
    Preferences,
    ProfileData,
    TailorResumePayload,
    TailoredResumeResult,
)
from src.services import llm

logger = logging.getLogger(__name__)


def _extract_pdf_links(reader: PdfReader) -> list[str]:
    links: list[str] = []
    for page in reader.pages:
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            action = annot.get("/A")
            if action and action.get("/S") == "/URI":
                uri = action.get("/URI")
                if uri and uri not in links:
                    links.append(uri)
    return links


def _categorize_links(links: list[str]) -> dict[str, str]:
    buckets = {"linkedin": "linkedin.com", "github": "github.com", "leetcode": "leetcode.com"}
    out: dict[str, str] = {}
    for url in links:
        for name, domain in buckets.items():
            if domain in url:
                out[name] = url
    return out


def _read_pdf(file_bytes: bytes) -> PdfReader:
    try:
        return PdfReader(io.BytesIO(file_bytes))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read PDF")


def _extract_pdf_text(reader: PdfReader) -> str:
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable text in PDF (is it a scanned image?)",
        )
    return text


def _infer_preferences(profile: Profile, profile_data: ProfileData) -> None:
    """Seed search prefs + years of experience from the résumé. Years is a factual attribute
    (always refresh it); search prefs are only seeded, never clobbering the user's own."""
    try:
        inferred = llm.infer_preferences(profile_data)
    except Exception as exc:  # noqa: BLE001 — inference is a nicety, never fail the parse
        logger.warning("preference inference failed: %s", exc)
        return

    profile_data.years_experience = inferred.years_experience

    prefs = Preferences.model_validate(profile.preferences or {})
    if prefs.titles:
        return  # user already has search prefs — don't overwrite them
    prefs.titles = inferred.titles
    prefs.seniority = inferred.seniority
    if profile_data.location and not prefs.locations:
        prefs.locations = [profile_data.location]
    profile.preferences = prefs.model_dump()


def create_profile_with_resume(email: str, file_bytes: bytes, db: Session) -> Profile:
    reader = _read_pdf(file_bytes)
    text = _extract_pdf_text(reader)
    links = _extract_pdf_links(reader)

    raw = llm.extract_resume(text)
    profile_data = ProfileData.model_validate(raw)

    categorized = _categorize_links(links)
    profile_data.linkedin = categorized.get("linkedin", profile_data.linkedin)
    profile_data.github = categorized.get("github", profile_data.github)

    promoted = {categorized.get("linkedin"), categorized.get("github")}
    profile_data.links = [
        url for url in links if url.startswith(("http://", "https://")) and url not in promoted
    ]

    profile = get_profile(email, db)

    if not profile:
        profile = Profile(email=email)
        db.add(profile)

    _infer_preferences(profile, profile_data)  # may set profile_data.years_experience
    profile.data = profile_data.model_dump()
    profile.name = profile_data.name

    db.commit()
    db.refresh(profile)
    return profile


def get_profile(email: str, db: Session) -> Profile | None:
    profile = db.query(Profile).filter(Profile.email == email).one_or_none()

    return profile


def update_profile_data(email: str, data: ProfileData, db: Session) -> Profile:
    profile = get_profile(email, db)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No profile found with the associated email: {email}",
        )

    profile.data = data.model_dump()
    profile.name = data.name or profile.name
    db.commit()
    db.refresh(profile)
    return profile


def set_preferences(email: str, preferences: Preferences, db: Session) -> Profile:
    profile = get_profile(email, db)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No profile found with the associated email: {email}",
        )

    profile.preferences = preferences.model_dump()
    db.commit()
    db.refresh(profile)
    return profile


def tailor_resume_to_job(payload: TailorResumePayload, db: Session) -> TailoredResumeResult:
    profile = get_profile(payload.email, db)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"No profile found with the associated email: {payload.email}"
        )

    profile_data = ProfileData.model_validate(profile.data)
    preferences = Preferences.model_validate(profile.preferences or {})

    try:
        tailored_resume = llm.tailor_resume(
            payload.company, payload.job_title, payload.job_description, profile_data, preferences
        )
    except llm.LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001 — convert provider errors to a stable API response
        logger.exception("resume tailoring provider failed for profile %s", profile.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The AI provider could not complete tailoring. Check the provider API key, "
                "credit balance, and model access in the server deployment."
            ),
        ) from exc

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
