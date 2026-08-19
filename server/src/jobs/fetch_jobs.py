"""Cron entrypoint: seed + discover companies, then fetch new jobs (LinkedIn included).

Run locally:   pipenv run python -m src.jobs.fetch_jobs
On Render:     a Cron Job service with this as its command.

This is the ONLY place include_linkedin=True is used — Apify runs on schedule, never on a
button. The interactive /jobs/refresh calls fetch_jobs(include_linkedin=False).
"""

import logging

from src.config.database import SessionLocal
from src.services import scraper_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    db = SessionLocal()
    try:
        seeded = scraper_service.seed_companies(db)
        # discover_companies() (Workable feed) is WIP — re-enable once its API mapping is fixed.
        new_jobs = scraper_service.fetch_jobs(db, include_linkedin=True)
        logger.info("seeded %s companies; fetched %s new jobs", seeded, new_jobs)
    finally:
        db.close()


if __name__ == "__main__":
    main()
