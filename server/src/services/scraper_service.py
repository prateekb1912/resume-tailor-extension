import logging
from datetime import datetime

from sqlalchemy.orm import Session

from src.config.enums import JobSource
from src.models import Company, Job
from src.services.scrapers import greenhouse
from src.utils.dedup import dedup_key

logger = logging.getLogger(__name__)

# Starter seed — well-known Greenhouse boards. Invalid slugs are skipped at fetch time.
# Real discovery (Common Crawl / Wayback, per the n8n seeding workflow) comes later.
_SEED_COMPANIES: list[tuple[str, str, str]] = [
    (JobSource.GREENHOUSE, "databricks", "Databricks"),
    (JobSource.GREENHOUSE, "coinbase", "Coinbase"),
    (JobSource.GREENHOUSE, "discord", "Discord"),
    (JobSource.GREENHOUSE, "robinhood", "Robinhood"),
    (JobSource.GREENHOUSE, "gitlab", "GitLab"),
    (JobSource.GREENHOUSE, "figma", "Figma"),
    (JobSource.GREENHOUSE, "plaid", "Plaid"),
    (JobSource.GREENHOUSE, "brex", "Brex"),
]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seed_companies(db: Session) -> int:
    added = 0
    for source, board, name in _SEED_COMPANIES:
        exists = db.query(Company).filter_by(source=source, board=board).first()
        if exists:
            continue
        db.add(Company(source=source, board=board, name=name, active=True))
        added += 1
    db.commit()
    return added


def fetch_jobs(db: Session) -> int:
    """Fetch every active Greenhouse company's jobs, dedup, store the new ones."""
    new_count = 0
    # Seen = keys already in the DB + keys added this run. dedup_key intentionally collapses
    # same-title/different-location postings (matches the n8n behavior).
    seen: set[str] = {key for (key,) in db.query(Job.dedup_key).all()}
    companies = db.query(Company).filter_by(active=True, source=JobSource.GREENHOUSE).all()

    for company in companies:
        try:
            raw_jobs = greenhouse.fetch_board(company.board)
        except Exception as exc:  # noqa: BLE001 — skip a dead board, keep going
            logger.warning("greenhouse fetch failed for %s: %s", company.board, exc)
            continue

        for raw in raw_jobs:
            key = dedup_key(company.name, raw["title"])
            if key in seen:
                continue
            seen.add(key)
            db.add(
                Job(
                    source=JobSource.GREENHOUSE,
                    external_id=raw["external_id"],
                    dedup_key=key,
                    title=raw["title"],
                    company=company.name,
                    location=raw["location"],
                    url=raw["url"],
                    description=raw["description"],
                    posted_at=_parse_dt(raw["posted_at"]),
                )
            )
            new_count += 1
        db.commit()
        logger.info("fetched %s (%s jobs on board)", company.board, len(raw_jobs))

    return new_count
