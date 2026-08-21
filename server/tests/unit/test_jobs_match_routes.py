import uuid
from types import SimpleNamespace

from src.models import Job, Profile
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


class _MatchedJobsQuery:
    def __init__(self, rows):
        self.rows = rows

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows


class _MatchedJobsDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *_models):
        return _MatchedJobsQuery(self.rows)


def test_list_jobs_exposes_match_explanation_and_missing_skills():
    profile = Profile(id=uuid.uuid4(), email="person@example.com", data={}, preferences={})
    job = Job(
        id=uuid.uuid4(),
        source="indeed",
        external_id="job-1",
        dedup_key="indeed:job-1",
        title="Platform Engineer",
        company="Example Corp",
        location="Remote",
        url="https://example.com/job-1",
        status="new",
    )
    match = SimpleNamespace(
        match_score=86,
        reason="Strong backend experience and relevant cloud infrastructure work.",
        missing_skills=["Kafka"],
    )

    result = jobs.list_jobs(q=None, profile=profile, db=_MatchedJobsDb([(job, match)]))

    assert result[0].match_score == 86
    assert result[0].reason == match.reason
    assert result[0].missing_skills == ["Kafka"]
