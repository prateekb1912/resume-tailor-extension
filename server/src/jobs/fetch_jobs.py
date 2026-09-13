"""Cron entrypoint: seed companies, fetch new jobs (paid sources optional), then auto-match
every onboarded profile so boards fill without anyone clicking Match.

Run locally:   pipenv run python -m src.jobs.fetch_jobs
On Render:     a Cron Job service with this as its command.

This is the batch ingestion entrypoint for free sources and optional paid sources. The
account-facing `/jobs/refresh` endpoint performs a preference-scoped paid refresh at most
once per UTC day and then matches, while `/jobs/match` only matches existing database rows.
"""

import logging
import os

from src.config.database import SessionLocal
from src.services import matching_service, scraper_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    # The daily schedule enables paid Apify sources; every-6h runs refresh only free sources.
    include_paid_sources = os.getenv("INCLUDE_PAID_SOURCES", "").lower() in ("1", "true", "yes")
    db = SessionLocal()
    try:
        seeded = scraper_service.seed_companies(db)
        new_jobs = scraper_service.fetch_jobs(db, include_paid_sources=include_paid_sources)
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
