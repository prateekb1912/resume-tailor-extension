from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

from src.schemas.profile import FitAssessment, Preferences, ProfileData, TailoredResumeResult
from src.config.settings import settings
from src.config.enums import ModelNames

_PARSE_SYSTEM_PROMPT = (
    "You are a precise resume parser. Extract the candidate's resume into the given "
    "structure. Use empty strings or empty arrays for anything not present. Do not "
    "invent, infer, or embellish any information."
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


def extract_resume(text: str) -> dict[str, Any]:
    model = ChatOpenAI(model=ModelNames.GPT_5_5, api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(
        model=model,
        system_prompt=_PARSE_SYSTEM_PROMPT,
        response_format=ProfileData,
    )
    response = agent.invoke({"messages": [{"role": "user", "content": f"Resume text:\n\n{text}"}]})
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


def tailor_resume(
    company: str,
    job_title: str,
    job_description: str,
    profile: ProfileData,
    preferences: Preferences,
) -> TailoredResumeResult:
    system_prompt = _TAILOR_RESUME_PROMPT.format(
        job_title=job_title,
        company=company,
        job_description=job_description,
        resume_profile=profile.model_dump_json(),
        preferences=_format_preferences(preferences),
    )
    model = ChatAnthropic(
        model_name=ModelNames.CLAUDE_SONNET_5,
        api_key=SecretStr(settings.anthropic_api_key),
        timeout=None,
        stop=None,
    )

    agent = create_agent(
        model=model, system_prompt=system_prompt, response_format=TailoredResumeResult
    )

    response = agent.invoke(
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
        }
    )

    return response["structured_response"]


# Fixed, person-agnostic screener scaffold. Everything opinionated is injected from the
# user's Preferences — so a different user (with different prefs) just gets different results.
_SCREEN_SYSTEM_PROMPT = """You are a strict job-fit screener helping a JOB SEEKER decide whether to apply. Do NOT write or rewrite a resume.

Judge fit on:
- Required must-have hard skills/tools the JD requires vs. what the resume clearly demonstrates.
- Required years/seniority vs. the candidate's actual experience.
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
    preferences: Preferences,
) -> FitAssessment:
    system_prompt = _SCREEN_SYSTEM_PROMPT.format(
        preferences=_format_preferences(preferences),
        instructions=preferences.screening_instructions or "None provided.",
    )
    model = ChatOpenAI(model=ModelNames.GPT_5_5, api_key=SecretStr(settings.openai_api_key))
    agent = create_agent(model=model, system_prompt=system_prompt, response_format=FitAssessment)

    user = (
        f"My resume:\n{profile.model_dump_json()}\n\n"
        f"Role:\nTitle: {title}\nCompany: {company}\nLocation: {location}\n\n"
        f"Job description:\n{description[:6000]}"
    )
    response = agent.invoke({"messages": [{"role": "user", "content": user}]})
    return response["structured_response"]
