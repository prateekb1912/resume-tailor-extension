import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.config.enums import JobSource
from src.config.settings import settings
from src.models import Company, Job, Profile
from src.services.scrapers import greenhouse, lever, linkedin_apify, workable
from src.utils.dedup import dedup_key

logger = logging.getLogger(__name__)

# Curated starter boards. Workable companies come from discover_companies() instead of a list.
_SEED_COMPANIES: list[tuple[str, str, str]] = [
    (JobSource.GREENHOUSE, "databricks", "Databricks"),
    (JobSource.GREENHOUSE, "coinbase", "Coinbase"),
    (JobSource.GREENHOUSE, "discord", "Discord"),
    (JobSource.GREENHOUSE, "robinhood", "Robinhood"),
    (JobSource.GREENHOUSE, "gitlab", "GitLab"),
    (JobSource.GREENHOUSE, "figma", "Figma"),
    (JobSource.GREENHOUSE, "plaid", "Plaid"),
    (JobSource.GREENHOUSE, "brex", "Brex"),
    # broader industries / strong HR + People volume (verified live against the ATS APIs)
    (JobSource.GREENHOUSE, "stripe", "Stripe"),
    (JobSource.GREENHOUSE, "mongodb", "MongoDB"),
    (JobSource.GREENHOUSE, "flexport", "Flexport"),
    (JobSource.GREENHOUSE, "samsara", "Samsara"),
    (JobSource.GREENHOUSE, "cloudflare", "Cloudflare"),
    (JobSource.GREENHOUSE, "airbnb", "Airbnb"),
    (JobSource.GREENHOUSE, "gusto", "Gusto"),
    (JobSource.GREENHOUSE, "asana", "Asana"),
    (JobSource.GREENHOUSE, "dropbox", "Dropbox"),
    (JobSource.LEVER, "palantir", "Palantir"),
    (JobSource.LEVER, "spotify", "Spotify"),
]

# Company-list ("board") sources. Workable is NOT here — it's a feed source (see below).
_BOARD_SCRAPERS = {
    JobSource.GREENHOUSE: greenhouse,
    JobSource.LEVER: lever,
}


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
        if db.query(Company).filter_by(source=source, board=board).first():
            continue
        db.add(Company(source=source, board=board, name=name, active=True))
        added += 1
    db.commit()
    return added


def _store(db: Session, items: list[dict[str, Any]], seen: set[str]) -> int:
    added = 0
    for it in items:
        if not it.get("title") or not it.get("company"):
            continue
        key = dedup_key(it["company"], it["title"])
        if key in seen:
            continue
        seen.add(key)
        db.add(
            Job(
                source=it["source"],
                external_id=it.get("external_id", ""),
                dedup_key=key,
                title=it["title"],
                company=it["company"],
                location=it.get("location"),
                url=it.get("url", ""),
                description=it.get("description") or "",
                posted_at=_parse_dt(it.get("posted_at")),
            )
        )
        added += 1
    db.commit()
    return added


def _board_items(db: Session, source: str) -> list[dict[str, Any]]:
    """Fetch every active company on a board source into the shared normalized shape."""
    scraper = _BOARD_SCRAPERS[source]
    items: list[dict[str, Any]] = []
    for company in db.query(Company).filter_by(active=True, source=source).all():
        try:
            raw_jobs = scraper.fetch_board(company.board)
        except Exception as exc:  # noqa: BLE001 — skip a dead board, keep going
            logger.warning("%s fetch failed for %s: %s", source, company.board, exc)
            continue
        for raw in raw_jobs:
            items.append({**raw, "source": source, "company": company.name})
    return items


def _pref_locations(db: Session) -> list[str]:
    """Distinct locations across all users' preferences — drives Workable feed queries."""
    locations: list[str] = []
    for (prefs,) in db.query(Profile.preferences).all():
        for loc in (prefs or {}).get("locations", []):
            if loc and loc not in locations:
                locations.append(loc)
    return locations[: settings.workable_max_locations]


def _workable_items(db: Session) -> list[dict[str, Any]]:
    """Feed-based discovery: query Workable's global feed per user location (no company list)."""
    locations = _pref_locations(db)
    if not locations:
        logger.info("no user preference locations configured — skipping Workable")
        return []
    items: list[dict[str, Any]] = []
    for location in locations:
        try:
            raw_jobs = workable.fetch_feed(location, max_pages=settings.workable_max_pages)
        except Exception as exc:  # noqa: BLE001 — skip a bad feed page, keep going
            logger.warning("workable feed failed for %s: %s", location, exc)
            continue
        for raw in raw_jobs:
            items.append({**raw, "source": JobSource.WORKABLE})
    return items


def _linkedin_titles(db: Session) -> list[str]:
    """Search titles come straight from what users configured in their preferences —
    never a hardcoded list. No users, no titles -> LinkedIn is skipped."""
    titles: list[str] = []
    for (prefs,) in db.query(Profile.preferences).all():
        for t in (prefs or {}).get("titles", []):
            if t and t not in titles:
                titles.append(t)
    return titles[: settings.apify_max_titles]


def _linkedin_items(db: Session) -> list[dict[str, Any]]:
    if not settings.apify_token:
        logger.warning("APIFY_TOKEN not set — skipping LinkedIn")
        return []
    titles = _linkedin_titles(db)
    if not titles:
        logger.info("no user preference titles configured — skipping LinkedIn")
        return []
    try:
        return linkedin_apify.fetch_jobs(
            titles,
            settings.apify_location,
            settings.apify_token,
            settings.apify_actor_id,
            settings.apify_count,
        )
    except Exception as exc:  # noqa: BLE001 — never let Apify failures kill the run
        logger.warning("linkedin/apify fetch failed: %s", exc)
        return []


def fetch_jobs(db: Session, include_linkedin: bool = False) -> int:
    """Fetch + store new jobs. Free board sources always run; include_linkedin=True is
    CRON ONLY (consumes Apify quota) — the manual /jobs/refresh must pass False."""
    seen: set[str] = {key for (key,) in db.query(Job.dedup_key).all()}
    new_count = 0
    # Free board sources (curated company lists).
    for source in (JobSource.GREENHOUSE, JobSource.LEVER):
        new_count += _store(db, _board_items(db, source), seen)
    # Free feed source (auto-discovery — any company hiring on Workable in a user's location).
    new_count += _store(db, _workable_items(db), seen)
    if include_linkedin:
        new_count += _store(db, _linkedin_items(db), seen)
    return new_count
