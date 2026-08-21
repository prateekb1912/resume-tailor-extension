from src.models import Profile
from src.routers import jobs


def test_legacy_refresh_matches_existing_jobs_without_scraping(monkeypatch):
    profile = Profile(email="person@example.com", data={}, preferences={})
    db = object()
    expected = {"candidates": 12, "screened": 8, "remaining": 4}

    monkeypatch.setattr(
        jobs.matching_service,
        "match_profile",
        lambda email, session: expected
        if (email, session) == (profile.email, db)
        else None,
    )
    monkeypatch.setattr(
        jobs.scraper_service,
        "fetch_jobs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not scrape")),
    )

    assert jobs.refresh_jobs(profile, db) == expected
