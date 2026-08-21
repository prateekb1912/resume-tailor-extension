import pytest

from src.schemas.profile import FitAssessment, Preferences, ProfileData, TailoredResumeResult
from src.services import llm


def _result() -> TailoredResumeResult:
    return TailoredResumeResult(
        profile=ProfileData(name="Test User"),
        fit=FitAssessment(match_score=75, reason="Good fit", missing_skills=[]),
    )


class _Agent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def invoke(self, _payload):
        if self.error:
            raise self.error
        return {"structured_response": self.result}


def test_tailor_uses_openai_when_anthropic_key_is_missing(monkeypatch):
    expected = _result()
    openai_model = object()

    monkeypatch.setattr(llm.settings, "anthropic_api_key", "")
    monkeypatch.setattr(llm.settings, "openai_api_key", "openai-test-key")
    monkeypatch.setattr(llm, "ChatOpenAI", lambda **_kwargs: openai_model)
    monkeypatch.setattr(
        llm,
        "ChatAnthropic",
        lambda **_kwargs: pytest.fail("Anthropic should not be initialized without a key"),
    )
    monkeypatch.setattr(
        llm,
        "create_agent",
        lambda **kwargs: _Agent(result=expected)
        if kwargs["model"] is openai_model
        else pytest.fail("Unexpected model"),
    )

    actual = llm.tailor_resume(
        "Example Co", "Engineer", "x" * 120, ProfileData(), Preferences()
    )

    assert actual == expected


def test_tailor_falls_back_to_openai_when_anthropic_fails(monkeypatch):
    expected = _result()
    anthropic_model = object()
    openai_model = object()

    monkeypatch.setattr(llm.settings, "anthropic_api_key", "anthropic-test-key")
    monkeypatch.setattr(llm.settings, "openai_api_key", "openai-test-key")
    monkeypatch.setattr(llm, "ChatAnthropic", lambda **_kwargs: anthropic_model)
    monkeypatch.setattr(llm, "ChatOpenAI", lambda **_kwargs: openai_model)

    def fake_agent(**kwargs):
        if kwargs["model"] is anthropic_model:
            return _Agent(error=RuntimeError("provider unavailable"))
        return _Agent(result=expected)

    monkeypatch.setattr(llm, "create_agent", fake_agent)

    actual = llm.tailor_resume(
        "Example Co", "Engineer", "x" * 120, ProfileData(), Preferences()
    )

    assert actual == expected


def test_tailor_reports_missing_provider_configuration(monkeypatch):
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "")
    monkeypatch.setattr(llm.settings, "openai_api_key", "")

    with pytest.raises(llm.LLMConfigurationError, match="ANTHROPIC_API_KEY or OPENAI_API_KEY"):
        llm.tailor_resume(
            "Example Co", "Engineer", "x" * 120, ProfileData(), Preferences()
        )
