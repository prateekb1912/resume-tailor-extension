import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.config.enums import ApplicationStatus
from src.config.settings import settings
from src.models import Job, JobMatch, Profile
from src.schemas.profile import Preferences, ProfileData
from src.services import llm, profile_service

logger = logging.getLogger(__name__)

_COMMIT_EVERY = 20  # flush JobMatch rows every N screens


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


def _screen_all(
    db: Session, profile: Profile, profile_data: ProfileData, prefs: Preferences, jobs: list[Job]
) -> int:
    """Screen jobs concurrently (LLM calls are I/O-bound). Worker threads only touch
    pre-extracted primitives + the LLM; every DB write stays on this (main) thread."""
    if not jobs:
        return 0

    # Pull the fields the LLM needs up front — no ORM/session access inside worker threads.
    payloads = [(j, j.title, j.company, j.location or "", j.description) for j in jobs]

    def screen(payload):
        job, title, company, location, description = payload
        return job, llm.screen_job(profile_data, title, company, location, description, prefs)

    screened = 0
    with ThreadPoolExecutor(max_workers=settings.match_workers) as pool:
        for future in as_completed([pool.submit(screen, p) for p in payloads]):
            try:
                job, fit = future.result()
            except Exception as exc:  # noqa: BLE001 — skip a bad screen, keep going
                logger.warning("screen failed: %s", exc)
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
            # Auto-park low-fit jobs in the "skipped" column (don't clobber user-moved cards).
            if job.status == ApplicationStatus.NEW.value and fit.match_score < prefs.min_match_score:
                job.status = ApplicationStatus.SKIPPED.value
            screened += 1
            if screened % _COMMIT_EVERY == 0:
                db.commit()
    db.commit()
    return screened


def match_profile(email: str, db: Session, limit: int | None = None) -> dict[str, int]:
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
    todo = [j for j in candidates if j.id not in already]
    if limit is not None:
        todo = todo[:limit]

    screened = _screen_all(db, profile, profile_data, prefs, todo)

    return {
        "candidates": len(candidates),
        "screened": screened,
        "remaining": max(0, len(candidates) - len(already) - screened),
    }


def match_active_profiles(db: Session) -> dict[str, int]:
    """Cron: screen all new (not-yet-matched) jobs for every onboarded profile (has a résumé
    + search titles), so boards fill without anyone clicking Match."""
    profiles = db.query(Profile).filter(Profile.email.isnot(None)).all()
    matched = screened = 0
    for profile in profiles:
        prefs = Preferences.model_validate(profile.preferences or {})
        if not prefs.titles or not (profile.data or {}).get("skills"):
            continue  # not onboarded enough to screen meaningfully
        try:
            result = match_profile(profile.email, db)
        except Exception as exc:  # noqa: BLE001 — one bad profile shouldn't stop the rest
            logger.warning("auto-match failed for %s: %s", profile.email, exc)
            continue
        screened += result["screened"]
        matched += 1
    return {"profiles_matched": matched, "jobs_screened": screened}
