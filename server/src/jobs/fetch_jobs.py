"""Cron entrypoint: seed companies, fetch new jobs (LinkedIn included), then auto-match
every onboarded profile so boards fill without anyone clicking Match.

Run locally:   pipenv run python -m src.jobs.fetch_jobs
On Render:     a Cron Job service with this as its command.

This is the ONLY place include_linkedin=True is used. The ordinary /jobs/refresh remains
free-source-only; the separate authenticated /jobs/refresh/linkedin endpoint runs only
LinkedIn and enforces one manual Apify trigger per account per UTC day.
"""

import logging
import os

from src.config.database import SessionLocal
from src.services import matching_service, scraper_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    # LinkedIn/Apify is rate-limited to once a day — the daily schedule sets INCLUDE_LINKEDIN;
    # the every-6h runs leave it unset and just refresh the free board sources.
    include_linkedin = os.getenv("INCLUDE_LINKEDIN", "").lower() in ("1", "true", "yes")
    db = SessionLocal()
    try:
        seeded = scraper_service.seed_companies(db)
        new_jobs = scraper_service.fetch_jobs(db, include_linkedin=include_linkedin)
        logger.info("seeded %s companies; fetched %s new jobs", seeded, new_jobs)
        matched = matching_service.match_active_profiles(db)
        logger.info(
            "auto-matched %s profiles; screened %s jobs",
            matched["profiles_matched"],
            matched["jobs_screened"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
