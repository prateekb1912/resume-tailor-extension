import uuid
from datetime import datetime, time, timedelta, timezone
from math import ceil

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from src.config.database import get_db
from src.config.dependencies import get_current_profile
from src.config.settings import settings
from src.models import Job, JobMatch, Profile
from src.schemas.job import JobResponse, JobStatusUpdate
from src.services import matching_service, scraper_service

router = APIRouter()


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _next_utc_day(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _linkedin_refresh_state(
    profile: Profile, now: datetime | None = None
) -> tuple[bool, datetime | None]:
    now = _utc(now or datetime.now(timezone.utc))
    last = profile.last_linkedin_refresh_at
    if last is None or _utc(last).date() < now.date():
        return True, None
    return False, _next_utc_day(now)


def _claim_linkedin_refresh(
    profile_id: uuid.UUID, db: Session, now: datetime | None = None
) -> datetime:
    """Atomically consume today's manual LinkedIn allowance for one profile."""
    now = _utc(now or datetime.now(timezone.utc))
    profile = (
        db.query(Profile)
        .filter(Profile.id == profile_id)
        .populate_existing()
        .with_for_update()
        .one()
    )
    allowed, next_reset = _linkedin_refresh_state(profile, now)
    if not allowed:
        retry_after = max(1, ceil((next_reset - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "LinkedIn can be refreshed manually once per account per UTC day.",
                "next_reset_at": next_reset.isoformat(),
            },
            headers={"Retry-After": str(retry_after)},
        )

    profile.last_linkedin_refresh_at = now
    db.commit()
    return _next_utc_day(now)


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


@router.post("/refresh", deprecated=True)
def refresh_jobs(
    profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Compatibility alias: account-facing refresh means match existing database jobs."""
    return matching_service.match_profile(profile.email, db)


@router.get("/refresh/linkedin")
def linkedin_refresh_status(
    profile: Profile = Depends(get_current_profile),
) -> dict[str, bool | str | None]:
    allowed, next_reset = _linkedin_refresh_state(profile)
    return {
        "allowed": allowed,
        "next_reset_at": next_reset.isoformat() if next_reset else None,
    }


@router.post("/refresh/linkedin")
def refresh_linkedin_jobs(
    profile: Profile = Depends(get_current_profile), db: Session = Depends(get_db)
) -> dict[str, int | str]:
    if not settings.apify_token.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LinkedIn refresh is unavailable because APIFY_TOKEN is not configured.",
        )

    titles: list[str] = []
    for value in (profile.preferences or {}).get("titles", []):
        title = value.strip() if isinstance(value, str) else ""
        if title and title not in titles:
            titles.append(title)
    if not titles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one target title in Preferences before refreshing LinkedIn.",
        )

    next_reset = _claim_linkedin_refresh(profile.id, db)
    fetched = scraper_service.fetch_linkedin_jobs(db, titles)
    return {"new_jobs": fetched, "next_reset_at": next_reset.isoformat()}
