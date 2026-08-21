"""Cron entrypoint: seed companies, fetch new jobs (paid sources optional), then auto-match
every onboarded profile so boards fill without anyone clicking Match.

Run locally:   pipenv run python -m src.jobs.fetch_jobs
On Render:     a Cron Job service with this as its command.

This is the ONLY place the global paid-source flags are used. The ordinary /jobs/refresh
remains free-source-only; the separate authenticated /jobs/refresh/linkedin endpoint runs
only LinkedIn and enforces one manual Apify trigger per account per UTC day.
"""

import logging
import os

from src.config.database import SessionLocal
from src.services import matching_service, scraper_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    # The daily schedule enables paid Apify sources; every-6h runs refresh only free sources.
    include_linkedin = os.getenv("INCLUDE_LINKEDIN", "").lower() in ("1", "true", "yes")
    include_aggregators = os.getenv("INCLUDE_AGGREGATORS", "").lower() in ("1", "true", "yes")
    db = SessionLocal()
    try:
        seeded = scraper_service.seed_companies(db)
        new_jobs = scraper_service.fetch_jobs(
            db,
            include_linkedin=include_linkedin,
            include_aggregators=include_aggregators,
        )
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
