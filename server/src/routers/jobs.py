import uuid

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from src.config.database import get_db
from src.config.dependencies import get_current_profile
from src.models import Job, JobMatch, Profile
from src.schemas.job import JobResponse, JobStatusUpdate
from src.services import matching_service, scraper_service

router = APIRouter()


@router.get("/", response_model=list[JobResponse])
def list_jobs(
    q: str | None = None,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> list[JobResponse]:
    # The signed-in user's screened feed (all matches, ranked). Low-fit jobs aren't
    # hidden — matching auto-parks them in the "skipped" column.
    rows = (
        db.query(Job, JobMatch)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .filter(JobMatch.profile_id == profile.id)
        .order_by(JobMatch.match_score.desc())
        .all()
    )
    result = []
    for job, match in rows:
        jr = JobResponse.model_validate(job)
        jr.match_score = match.match_score
        jr.reason = match.reason
        result.append(jr)

    if q:
        needle = q.lower()
        result = [r for r in result if needle in r.title.lower() or needle in r.company.lower()]
    return result


@router.post("/match")
def match_jobs(
    profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)
) -> dict[str, int]:
    return matching_service.match_profile(profile.email, db)


@router.patch("/{job_id}", response_model=JobResponse)
def update_status(
    job_id: uuid.UUID,
    payload: JobStatusUpdate,
    profile: Profile = Depends(get_current_profile),
    db: Session = Depends(get_db),
) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job.status = payload.status.value
    db.commit()
    db.refresh(job)
    return job


@router.post("/refresh")
def refresh_jobs(
    profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)
) -> dict[str, int]:
    seeded = scraper_service.seed_companies(db)
    fetched = scraper_service.fetch_jobs(db)
    return {"companies_seeded": seeded, "new_jobs": fetched}
