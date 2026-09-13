import uuid
from types import SimpleNamespace

from src.models import Job, Profile
from src.routers import jobs
from src.schemas.job import JobTitleSearch
from src.schemas.profile import Preferences


def test_refresh_still_matches_when_fresh_job_source_is_not_configured(monkeypatch):
    profile = Profile(
        email="person@example.com", data={}, preferences={"titles": ["Platform Engineer"]}
    )
    db = object()
    expected = {"candidates": 12, "screened": 8, "remaining": 4}

    monkeypatch.setattr(jobs.settings, "apify_token", "")

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

    assert jobs.refresh_jobs(profile, db) == {
        "new_jobs": 0,
        "fetch_status": "not_configured",
        "next_reset_at": None,
        **expected,
    }


def test_title_search_replaces_only_titles_then_refreshes(monkeypatch):
    profile = Profile(
        email="person@example.com",
        data={},
        preferences={
            "titles": ["Old title"],
            "locations": ["Bengaluru"],
            "seniority": ["senior"],
            "work_types": ["hybrid"],
            "exclude_companies": ["Example Corp"],
            "exclude_keywords": ["sales"],
            "open_to_relocation": True,
            "max_age_days": 14,
            "min_match_score": 72,
            "screening_instructions": "Prefer implementation roles.",
        },
    )
    db = object()
    original = Preferences.model_validate(profile.preferences)
    captured = {}

    def set_preferences(email, preferences, session):
        captured.update(email=email, preferences=preferences, session=session)
        profile.preferences = preferences.model_dump()
        return profile

    monkeypatch.setattr(jobs.profile_service, "set_preferences", set_preferences)
    monkeypatch.setattr(
        jobs,
        "refresh_jobs",
        lambda updated, session: {"new_jobs": 2, "screened": 3},
    )

    result = jobs.search_jobs(JobTitleSearch(title="  HRBP  "), profile, db)

    assert result == {"new_jobs": 2, "screened": 3}
    assert captured["email"] == profile.email
    assert captured["session"] is db
    updated = captured["preferences"]
    assert updated.titles == ["HRBP"]
    assert updated.model_copy(update={"titles": original.titles}) == original


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
