import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.models import Job, JobMatch
from src.schemas.profile import Preferences, ProfileData
from src.services import llm, profile_service

logger = logging.getLogger(__name__)

_SCREEN_LIMIT = 25  # max LLM screens per run — keeps cost/latency bounded


def _prefilter(jobs: list[Job], prefs: Preferences) -> list[Job]:
    """Cheap, no-LLM Layer-1 filter (ported from the n8n scrapers), driven by preferences."""
    titles = [t.lower() for t in prefs.titles]
    locations = [loc.lower() for loc in prefs.locations]
    excluded = {c.lower() for c in prefs.exclude_companies}
    cutoff = datetime.now(timezone.utc) - timedelta(days=prefs.max_age_days or 3650)

    kept: list[Job] = []
    for job in jobs:
        if job.company.lower() in excluded:
            continue
        if job.posted_at is not None and job.posted_at < cutoff:
            continue
        if titles and not any(t in job.title.lower() for t in titles):
            continue
        if locations and job.location and not any(loc in job.location.lower() for loc in locations):
            continue
        kept.append(job)
    return kept


def match_profile(email: str, db: Session, limit: int = _SCREEN_LIMIT) -> dict[str, int]:
    profile = profile_service.get_profile(email, db)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No profile found with the associated email: {email}",
        )
    prefs = Preferences.model_validate(profile.preferences or {})
    profile_data = ProfileData.model_validate(profile.data)

    candidates = _prefilter(db.query(Job).all(), prefs)
    already = {
        job_id for (job_id,) in db.query(JobMatch.job_id).filter(JobMatch.profile_id == profile.id)
    }
    todo = [j for j in candidates if j.id not in already][:limit]

    screened = 0
    for job in todo:
        try:
            fit = llm.screen_job(
                profile_data, job.title, job.company, job.location or "", job.description, prefs
            )
        except Exception as exc:  # noqa: BLE001 — skip a bad screen, keep going
            logger.warning("screen failed for job %s: %s", job.id, exc)
            continue
        db.add(
            JobMatch(
                profile_id=profile.id,
                job_id=job.id,
                match_score=fit.match_score,
                reason=fit.reason,
                missing_skills=fit.missing_skills,
            )
        )
        screened += 1
    db.commit()

    return {
        "candidates": len(candidates),
        "screened": screened,
        "remaining": max(0, len(candidates) - len(already) - len(todo)),
    }
