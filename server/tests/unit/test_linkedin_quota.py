import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.models import Profile
from src.routers import jobs


class _ProfileQuery:
    def __init__(self, profile):
        self.profile = profile

    def filter(self, *_args):
        return self

    def populate_existing(self):
        return self

    def with_for_update(self):
        return self

    def one(self):
        return self.profile


class _Db:
    def __init__(self, profile):
        self.profile = profile
        self.commits = 0

    def query(self, _model):
        return _ProfileQuery(self.profile)

    def commit(self):
        self.commits += 1


def _profile() -> Profile:
    return Profile(
        id=uuid.uuid4(),
        email="person@example.com",
        data={},
        preferences={"titles": ["Backend Engineer"]},
    )


def test_first_manual_linkedin_refresh_claim_is_allowed():
    profile = _profile()
    db = _Db(profile)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    reset = jobs._claim_linkedin_refresh(profile.id, db, now)

    assert profile.last_linkedin_refresh_at == now
    assert reset == datetime(2026, 8, 21, tzinfo=timezone.utc)
    assert db.commits == 1


def test_second_manual_linkedin_refresh_same_utc_day_is_rejected():
    profile = _profile()
    profile.last_linkedin_refresh_at = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
    db = _Db(profile)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(HTTPException) as raised:
        jobs._claim_linkedin_refresh(profile.id, db, now)

    assert raised.value.status_code == 429
    assert raised.value.headers["Retry-After"] == "43200"
    assert raised.value.detail["next_reset_at"] == "2026-08-21T00:00:00+00:00"
    assert db.commits == 0


def test_manual_linkedin_refresh_resets_on_next_utc_day():
    profile = _profile()
    profile.last_linkedin_refresh_at = datetime(2026, 8, 20, 23, 59, tzinfo=timezone.utc)
    db = _Db(profile)
    now = profile.last_linkedin_refresh_at + timedelta(minutes=2)

    jobs._claim_linkedin_refresh(profile.id, db, now)

    assert profile.last_linkedin_refresh_at == now
    assert db.commits == 1
