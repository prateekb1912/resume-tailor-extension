import uuid

from pydantic import EmailStr
from sqlalchemy import nulls_last
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from src.config.database import get_db
from src.models import Job, JobMatch
from src.schemas.job import JobResponse, JobStatusUpdate, MatchRequest
from src.schemas.profile import Preferences
from src.services import matching_service, profile_service, scraper_service

router = APIRouter()

_LIMIT = 500


@router.get("/", response_model=list[JobResponse])
def list_jobs(
    email: EmailStr | None = None,
    q: str | None = None,
    min_score: int | None = None,
    db: Session = Depends(get_db),
) -> list[JobResponse]:
    # With email -> the user's screened feed (jobs joined with their match scores, ranked).
    # Low-fit jobs are hidden by default: threshold = the profile's min_match_score
    # unless overridden by ?min_score= (pass min_score=0 to see everything).
    if email:
        profile = profile_service.get_profile(email, db)
        if not profile:
            return []
        prefs = Preferences.model_validate(profile.preferences or {})
        threshold = min_score if min_score is not None else prefs.min_match_score
        rows = (
            db.query(Job, JobMatch)
            .join(JobMatch, JobMatch.job_id == Job.id)
            .filter(JobMatch.profile_id == profile.id, JobMatch.match_score >= threshold)
            .order_by(JobMatch.match_score.desc())
            .all()
        )
        result = []
        for job, match in rows:
            jr = JobResponse.model_validate(job)
            jr.match_score = match.match_score
            jr.reason = match.reason
            result.append(jr)
    else:
        jobs = db.query(Job).order_by(nulls_last(Job.posted_at.desc())).limit(_LIMIT).all()
        result = [JobResponse.model_validate(j) for j in jobs]

    if q:
        needle = q.lower()
        result = [r for r in result if needle in r.title.lower() or needle in r.company.lower()]
    return result


@router.post("/match")
def match_jobs(payload: MatchRequest, db: Session = Depends(get_db)) -> dict[str, int]:
    return matching_service.match_profile(payload.email, db)


@router.patch("/{job_id}", response_model=JobResponse)
def update_status(
    job_id: uuid.UUID, payload: JobStatusUpdate, db: Session = Depends(get_db)
) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job.status = payload.status.value
    db.commit()
    db.refresh(job)
    return job


@router.post("/refresh")
def refresh_jobs(db: Session = Depends(get_db)) -> dict[str, int]:
    seeded = scraper_service.seed_companies(db)
    fetched = scraper_service.fetch_jobs(db)
    return {"companies_seeded": seeded, "new_jobs": fetched}
