import json
import logging
import time
import uuid
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

from src.schemas.profile import (
    FitAssessment,
    InferredPreferences,
    Preferences,
    ProfileData,
    TailoredResumeResult,
)
from src.config.settings import settings
from src.config.enums import ModelNames

logger = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    """Raised when no configured provider can serve an LLM request."""


def _model_name(value: Any) -> str:
    return str(getattr(value, "value", value))


def _token_usage(response: Any) -> dict[str, int]:
    """Extract LangChain token metadata when the provider returned it."""
    if not isinstance(response, dict):
        return {}
    for message in reversed(response.get("messages") or []):
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            metadata = getattr(message, "response_metadata", None) or {}
            usage = metadata.get("token_usage") or metadata.get("usage")
        if isinstance(usage, dict):
            return {
                str(key): int(value)
                for key, value in usage.items()
                if isinstance(value, (int, float))
            }
    return {}


def _invoke_logged(
    agent: Any,
    payload: dict[str, Any],
    *,
    operation: str,
    provider: str,
    model: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke an agent and emit safe structured lifecycle logs without prompt contents."""
    run_id = str(uuid.uuid4())
    base = {
        "event": "llm_run",
        "run_id": run_id,
        "operation": operation,
        "provider": provider,
        "model": _model_name(model),
        **{key: value for key, value in (metadata or {}).items() if value is not None},
    }
    logger.info(json.dumps({**base, "status": "started"}, default=str, sort_keys=True))
    started = time.perf_counter()
    try:
        response = agent.invoke(payload)
    except Exception as exc:
        logger.exception(
            json.dumps(
                {
                    **base,
                    "status": "error",
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "error_type": type(exc).__name__,
                },
                default=str,
                sort_keys=True,
            )
        )
        raise

    completed = {
        **base,
        "status": "completed",
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }
    usage = _token_usage(response)
    if usage:
        completed["token_usage"] = usage
    logger.info(json.dumps(completed, default=str, sort_keys=True))
    return response

_PARSE_SYSTEM_PROMPT = (
    "You are a precise resume parser. Extract the candidate's resume into the given "
    "structure. Use empty strings or empty arrays for anything not present. Do not "
    "invent, infer, or embellish any information. Store experience and education dates "
    "at month precision in YYYY-MM format. For an ongoing job or education, set current "
    "to true and leave endDate empty."
)

_TAILOR_RESUME_PROMPT = """
    You are a senior recruiter, resume tailor, and strict job-fit screener for {company}.

    Your job is to tailor the resume profile for this specific role and assess how well
    the candidate fits it. Perform both tasks in one response.

    Follow these rules strictly:

    **ANALYSIS (internal, do not output):**
    - Identify the top 5 missing keywords from the JD that are absent or underrepresented in the resume
    - Identify up to 3 red flags a hiring manager would spot in under 10 seconds
    - Score the candidate against the JD using only evidence in the original resume
    - Identify the job title and hiring company. Use the provided values if they look
      correct; otherwise infer them from the job description. Return the company's plain
      brand name (for example, "Okta", not "Okta, Inc.")

    **FIT SCREENING RULES:**
    - Judge required skills: compare the JD's must-have hard skills, tools, and
      technologies with what the original resume demonstrates
    - Judge experience: compare required years, seniority, and level with the candidate's
      demonstrated experience
    - Judge domain alignment with the candidate's background
    - Judge location and work-type compatibility against the candidate preferences below
    - REJECT if the role requires any of the candidate's excluded skills/keywords, is at an
      excluded company, or is a work type the candidate is not open to
    - Produce an integer match score from 0 to 100
    - Set decision to "REJECT" if the match score is below 60, the candidate is missing
      the majority of must-have hard skills, or the required experience clearly exceeds
      theirs; otherwise set it to "PROCEED"
    - Keep the fit assessment honest. Do not increase the score based on wording added
      during tailoring; score only capabilities supported by the original resume

    **REWRITING RULES:**
    - Rewrite every bullet point using the XYZ formula: "Accomplished [X] as measured by [Y] by doing [Z]" — make it specific, quantified where possible, but not necessarily use Accomplished everytime to avoid repetition
    - Naturally weave in the missing keywords across the summary, bullets, and skills — never keyword-stuff, always contextually accurate
    - Remove or reframe any red flags (gaps, vague language, irrelevant roles, weak verbs)
    - Rewrite the summary to speak directly to this role and company
    - If any experience doesn't have any summary, don't add anything on your own
    - Reorder skills — most relevant to this JD first
    - Every bullet must earn its place
    - Do NOT invent experience, titles, companies, dates, or credentials
    - Only add a skill if it appears in the experience/projects or is a direct sub-technology of an existing skill
    - Keep all dates, titles, and company names exactly as-is
    **OUTPUT:**
    Return ONLY raw JSON matching the configured structured-output schema. It must contain:
    - profile: the tailored resume in the same structure as the input profile
    - fit: an object containing decision, match_score, reason, missing_skills, title,
      and company

    Keep reason to one or two sentences. missing_skills must contain only missing
    must-have skills, or an empty list when none are missing. Do not return markdown,
    explanations, a preamble, or the internal analysis.

    CANDIDATE PREFERENCES:
    {preferences}

    Job Title: {job_title}
    Company: {company}

    Job Description:
    {job_description}

    Resume Profile:
    {resume_profile}
"""


def extract_resume(text: str, *, profile_id: Any = None) -> dict[str, Any]:
    model = ChatOpenAI(model=ModelNames.GPT_5_5, api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(
        model=model,
        system_prompt=_PARSE_SYSTEM_PROMPT,
        response_format=ProfileData,
    )
    response = _invoke_logged(
        agent,
        {"messages": [{"role": "user", "content": f"Resume text:\n\n{text}"}]},
        operation="resume_parse",
        provider="openai",
        model=ModelNames.GPT_5_5,
        metadata={"profile_id": profile_id, "input_chars": len(text)},
    )
    return response["structured_response"]


_INFER_PREFS_PROMPT = (
    "From the candidate's resume, infer sensible DEFAULT job-search preferences.\n"
    "- titles: 3-6 concise, canonical job titles they should search for. Strip seniority "
    "prefixes and suffixes (return 'Backend Engineer', not 'Senior Backend Engineer II') so "
    "the search matches broadly. Base them on their actual experience and skills.\n"
    "- seniority: their level(s) as lowercase tags from: intern, junior, mid, senior, staff, "
    "lead, principal, manager, director.\n"
    "- years_experience: total professional years of experience as a number. Sum the work "
    "history, ignore overlaps, count internships as partial years. Exclude education-only time."
)


def infer_preferences(profile: ProfileData, *, profile_id: Any = None) -> InferredPreferences:
    """One cheap call to seed a new user's search prefs so matching is relevant day one."""
    model = ChatOpenAI(model=ModelNames.GPT_5_5, api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(
        model=model, system_prompt=_INFER_PREFS_PROMPT, response_format=InferredPreferences
    )
    response = _invoke_logged(
        agent,
        {"messages": [{"role": "user", "content": profile.model_dump_json()}]},
        operation="preference_inference",
        provider="openai",
        model=ModelNames.GPT_5_5,
        metadata={"profile_id": profile_id},
    )
    return response["structured_response"]


def _format_preferences(preferences: Preferences) -> str:
    lines: list[str] = []
    if preferences.locations:
        lines.append(f"- Open to locations: {', '.join(preferences.locations)}")
    if preferences.work_types:
        lines.append(f"- Work types: {', '.join(w.value for w in preferences.work_types)}")
    if preferences.seniority:
        lines.append(f"- Seniority levels: {', '.join(preferences.seniority)}")
    if preferences.titles:
        lines.append(f"- Target titles: {', '.join(preferences.titles)}")
    if preferences.exclude_keywords:
        lines.append(f"- Reject if the role requires: {', '.join(preferences.exclude_keywords)}")
    if preferences.exclude_companies:
        lines.append(f"- Exclude companies: {', '.join(preferences.exclude_companies)}")
    if preferences.open_to_relocation:
        lines.append("- Open to relocation")
    return "\n    ".join(lines) if lines else "- No specific preferences provided"


def _invoke_tailor_agent(
    model: Any,
    system_prompt: str,
    *,
    provider: str,
    model_name: Any,
    metadata: dict[str, Any],
) -> TailoredResumeResult:
    agent = create_agent(
        model=model, system_prompt=system_prompt, response_format=TailoredResumeResult
    )
    response = _invoke_logged(
        agent,
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Tailor the resume for the provided role and assess the candidate's "
                        "fit. Return only the configured structured response."
                    ),
                }
            ]
        },
        operation="resume_tailor",
        provider=provider,
        model=model_name,
        metadata=metadata,
    )
    return response["structured_response"]


def tailor_resume(
    company: str,
    job_title: str,
    job_description: str,
    profile: ProfileData,
    preferences: Preferences,
    *,
    profile_id: Any = None,
) -> TailoredResumeResult:
    system_prompt = _TAILOR_RESUME_PROMPT.format(
        job_title=job_title,
        company=company,
        job_description=job_description,
        resume_profile=profile.model_dump_json(),
        preferences=_format_preferences(preferences),
    )

    anthropic_key = settings.anthropic_api_key.strip()
    openai_key = settings.openai_api_key.strip()
    run_metadata = {
        "profile_id": profile_id,
        "job_title": job_title,
        "company": company,
        "jd_chars": len(job_description),
    }

    if anthropic_key:
        try:
            model = ChatAnthropic(
                model_name=ModelNames.CLAUDE_SONNET_5,
                api_key=SecretStr(anthropic_key),
                timeout=None,
                stop=None,
            )
            return _invoke_tailor_agent(
                model,
                system_prompt,
                provider="anthropic",
                model_name=ModelNames.CLAUDE_SONNET_5,
                metadata=run_metadata,
            )
        except Exception:  # noqa: BLE001 — retry the configured fallback provider
            if not openai_key:
                raise
            logger.exception("Anthropic tailoring failed; retrying with OpenAI")

    if openai_key:
        if not anthropic_key:
            logger.warning("ANTHROPIC_API_KEY is not set; using OpenAI for tailoring")
        model = ChatOpenAI(model=ModelNames.GPT_5_5, api_key=SecretStr(openai_key))
        return _invoke_tailor_agent(
            model,
            system_prompt,
            provider="openai",
            model_name=ModelNames.GPT_5_5,
            metadata=run_metadata,
        )

    raise LLMConfigurationError(
        "Tailoring is not configured: set ANTHROPIC_API_KEY or OPENAI_API_KEY on the server."
    )


# Fixed, person-agnostic screener scaffold. Everything opinionated is injected from the
# user's Preferences — so a different user (with different prefs) just gets different results.
_SCREEN_SYSTEM_PROMPT = """You are a strict job-fit screener helping a JOB SEEKER decide whether to apply. Do NOT write or rewrite a resume.

Judge fit on:
- Required must-have hard skills/tools the JD requires vs. what the resume clearly demonstrates.
- Required years of experience in the JD vs. the candidate's total years (stated below). Penalize
  clearly when the JD demands materially more experience than the candidate has; don't over-penalize
  a small gap.
- Seniority level fit.
- Domain alignment with the candidate's background.
- Location and work-type compatibility with the preferences below.

CANDIDATE PREFERENCES:
{preferences}

CANDIDATE-SPECIFIC CRITERIA (the candidate's own words — weight these heavily):
{instructions}

Return an integer match_score (0-100), a one or two sentence reason, and missing_skills
(the must-have skills the candidate lacks, or an empty list when none are missing)."""


def screen_job(
    profile: ProfileData, title: str, company: str, location: str, description: str,
    preferences: Preferences, *, profile_id: Any = None, job_id: Any = None,
    match_run_id: str | None = None,
) -> FitAssessment:
    system_prompt = _SCREEN_SYSTEM_PROMPT.format(
        preferences=_format_preferences(preferences),
        instructions=preferences.screening_instructions or "None provided.",
    )
    model = ChatOpenAI(model=ModelNames.GPT_5_5, api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(model=model, system_prompt=system_prompt, response_format=FitAssessment)

    user = (
        f"My resume:\n{profile.model_dump_json()}\n\n"
        f"Candidate total years of experience: {profile.years_experience}\n\n"
        f"Role:\nTitle: {title}\nCompany: {company}\nLocation: {location}\n\n"
        f"Job description:\n{description[:6000]}"
    )
    response = _invoke_logged(
        agent,
        {"messages": [{"role": "user", "content": user}]},
        operation="job_screen",
        provider="openai",
        model=ModelNames.GPT_5_5,
        metadata={
            "profile_id": profile_id,
            "job_id": job_id,
            "match_run_id": match_run_id,
            "job_title": title,
            "company": company,
            "jd_chars": len(description),
        },
    )
    return response["structured_response"]
