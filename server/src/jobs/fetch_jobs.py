"""Cron entrypoint: seed companies + fetch new jobs.

Run locally:   pipenv run python -m src.jobs.fetch_jobs
On Render:     a Cron Job service with this as its command.
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
        new_jobs = scraper_service.fetch_jobs(db)
        logger.info("seeded %s companies, fetched %s new jobs", seeded, new_jobs)
    finally:
        db.close()


if __name__ == "__main__":
    main()
