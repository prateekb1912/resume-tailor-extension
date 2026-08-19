"""Cron entrypoint: seed companies, fetch new jobs (LinkedIn included), then auto-match
every onboarded profile so boards fill without anyone clicking Match.

Run locally:   pipenv run python -m src.jobs.fetch_jobs
On Render:     a Cron Job service with this as its command.

This is the ONLY place include_linkedin=True is used — Apify runs on schedule, never on a
button. The interactive /jobs/refresh calls fetch_jobs(include_linkedin=False).
"""

import logging

from src.config.database import SessionLocal
from src.services import matching_service, scraper_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    db = SessionLocal()
    try:
        seeded = scraper_service.seed_companies(db)
        new_jobs = scraper_service.fetch_jobs(db, include_linkedin=True)
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
