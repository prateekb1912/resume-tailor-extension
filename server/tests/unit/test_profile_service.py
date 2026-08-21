from src.config.enums import WorkType
from src.models import Profile
from src.schemas.profile import InferredPreferences, ProfileData
from src.services import llm, profile_service


class _ProfileQuery:
    def __init__(self, profile: Profile):
        self.profile = profile

    def filter(self, *_args):
        return self

    def one_or_none(self):
        return self.profile


class _Db:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.committed = False

    def query(self, _model):
        return _ProfileQuery(self.profile)

    def commit(self):
        self.committed = True

    def refresh(self, _profile):
        pass


def test_profile_update_refreshes_derived_preferences_and_keeps_manual_filters(monkeypatch):
    profile = Profile(
        email="person@example.com",
        data={},
        preferences={
            "titles": ["Old title"],
            "locations": ["Old location", "Remote"],
            "seniority": ["old"],
            "work_types": ["remote"],
            "exclude_companies": ["Example Corp"],
            "min_match_score": 75,
            "screening_instructions": "Prefer backend-heavy roles.",
        },
    )
    db = _Db(profile)
    data = ProfileData(name="Test User", location="Bengaluru")
    monkeypatch.setattr(
        llm,
        "infer_preferences",
        lambda _data: InferredPreferences(
            titles=["Backend Engineer", "Platform Engineer"],
            seniority=["senior"],
            years_experience=6.5,
        ),
    )

    updated = profile_service.update_profile_data(profile.email, data, db)

    assert db.committed
    assert updated.preferences["titles"] == ["Backend Engineer", "Platform Engineer"]
    assert updated.preferences["locations"] == ["Bengaluru"]
    assert updated.preferences["seniority"] == ["senior"]
    assert updated.preferences["work_types"] == [WorkType.REMOTE]
    assert updated.preferences["exclude_companies"] == ["Example Corp"]
    assert updated.preferences["min_match_score"] == 75
    assert updated.preferences["screening_instructions"] == "Prefer backend-heavy roles."
    assert updated.data["years_experience"] == 6.5


def test_profile_update_still_saves_when_preference_inference_fails(monkeypatch):
    profile = Profile(
        email="person@example.com",
        data={},
        preferences={"titles": ["Keep this title"]},
    )
    db = _Db(profile)

    def fail(_data):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(llm, "infer_preferences", fail)

    updated = profile_service.update_profile_data(
        profile.email, ProfileData(name="Updated name"), db
    )

    assert db.committed
    assert updated.name == "Updated name"
    assert updated.preferences["titles"] == ["Keep this title"]
