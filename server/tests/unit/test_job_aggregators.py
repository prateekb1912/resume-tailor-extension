from datetime import datetime, timezone

from src.config.enums import JobSource
from src.services import scraper_service
from src.services.scrapers import indeed_apify, naukri_apify


class _Response:
    def __init__(self, items):
        self.items = items

    def raise_for_status(self):
        pass

    def json(self):
        return self.items


class _PreferencesQuery:
    def __init__(self, preferences):
        self.preferences = preferences

    def all(self):
        return [(preferences,) for preferences in self.preferences]


class _PreferencesDb:
    def __init__(self, preferences):
        self.preferences = preferences

    def query(self, _column):
        return _PreferencesQuery(self.preferences)


def test_aggregator_queries_follow_account_preferences_and_cap(monkeypatch):
    monkeypatch.setattr(scraper_service.settings, "apify_aggregator_max_queries", 3)
    db = _PreferencesDb(
        [
            {
                "titles": ["Backend Engineer", "Platform Engineer"],
                "locations": ["Bengaluru", "Remote"],
            },
            {"titles": ["Data Engineer"], "locations": ["Pune"]},
        ]
    )

    assert scraper_service._aggregator_queries(db) == [
        ("Backend Engineer", "Bengaluru"),
        ("Data Engineer", "Pune"),
        ("Backend Engineer", "Remote"),
    ]


def test_indeed_actor_request_and_normalization(monkeypatch):
    request = {}

    def post(url, json, timeout):
        request.update(url=url, json=json, timeout=timeout)
        return _Response(
            [
                {
                    "id": "abc123",
                    "positionName": "Backend Engineer",
                    "company": "Example Co",
                    "location": "Bengaluru",
                    "description": "Build and operate backend services for a large distributed platform.",
                    "postingDateParsed": "2026-08-21",
                }
            ]
        )

    monkeypatch.setattr(indeed_apify.httpx, "post", post)

    jobs = indeed_apify.fetch_jobs(
        [("Backend Engineer", "Bengaluru")], "token", "actor~id", "IN", 10
    )

    assert request["json"]["position"] == "Backend Engineer"
    assert request["json"]["country"] == "IN"
    assert request["json"]["maxItemsPerSearch"] == 10
    assert jobs == [
        {
            "source": JobSource.INDEED,
            "external_id": "abc123",
            "title": "Backend Engineer",
            "company": "Example Co",
            "location": "Bengaluru",
            "url": "https://in.indeed.com/viewjob?jk=abc123",
            "description": "Build and operate backend services for a large distributed platform.",
            "posted_at": "2026-08-21",
        }
    ]


def test_naukri_actor_request_and_normalization(monkeypatch):
    created = datetime(2026, 8, 21, 10, 30, tzinfo=timezone.utc)
    request = {}

    def post(url, json, timeout):
        request.update(url=url, json=json, timeout=timeout)
        return _Response(
            [
                {
                    "jobId": "210826000001",
                    "title": "Platform Engineer",
                    "companyName": "Example India",
                    "locationLabel": "Hybrid - Bengaluru",
                    "jdURL": "/job-listings-platform-engineer-example",
                    "jobDescription": "Own reliable platform services and developer infrastructure.",
                    "tagsAndSkills": ["Python", "Kubernetes"],
                    "experienceLabel": "3-6 Yrs",
                    "createdDate": int(created.timestamp() * 1000),
                }
            ]
        )

    monkeypatch.setattr(naukri_apify.httpx, "post", post)

    jobs = naukri_apify.fetch_jobs(
        [("Platform Engineer", "Bengaluru")], "token", "actor~id", 10
    )

    assert request["json"]["keyword"] == "Platform Engineer"
    assert request["json"]["jobAge"] == "7"
    assert request["json"]["maxResultsPerQuery"] == 10
    assert jobs[0]["source"] == JobSource.NAUKRI
    assert jobs[0]["external_id"] == "210826000001"
    assert jobs[0]["url"] == (
        "https://www.naukri.com/job-listings-platform-engineer-example"
    )
    assert "Skills: Python, Kubernetes" in jobs[0]["description"]
    assert jobs[0]["posted_at"] == created.isoformat()


def test_actor_continues_after_one_query_fails(monkeypatch):
    calls = 0

    def post(_url, json, timeout):
        nonlocal calls
        del timeout
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary actor failure")
        return _Response(
            [
                {
                    "id": "second-query-job",
                    "positionName": json["position"],
                    "company": "Example Co",
                    "description": "A sufficiently detailed description for the second query result.",
                }
            ]
        )

    monkeypatch.setattr(indeed_apify.httpx, "post", post)

    jobs = indeed_apify.fetch_jobs(
        [("First", "Bengaluru"), ("Second", "Pune")],
        "token",
        "actor~id",
        "IN",
        10,
    )

    assert calls == 2
    assert [job["title"] for job in jobs] == ["Second"]
