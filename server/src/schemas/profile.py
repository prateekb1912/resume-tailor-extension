from pydantic import BaseModel, ConfigDict, Field, EmailStr

from src.config.enums import WorkType


class Experience(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    company: str = ""
    startDate: str = ""
    endDate: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    model_config = ConfigDict(extra="ignore")

    degree: str = ""
    school: str = ""
    year: str = ""
    gpa: str = ""


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    description: str = ""
    bullets: list[str] = Field(default_factory=list)


class ProfileData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    links: list[str] = Field(default_factory=list)
    years_experience: float = 0  # total professional YOE, inferred on parse
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    locations: list[str] = Field(default_factory=list)       # ["Bengaluru", "India", "Remote"]
    titles: list[str] = Field(default_factory=list)          # roles to search/tailor toward
    work_types: list[WorkType] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)       # ["mid", "senior"] — judged by the LLM
    exclude_companies: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)  # reject if the JD requires these
    open_to_relocation: bool = False

    max_age_days: int = 7          # freshness prefilter
    min_match_score: int = 60      # PROCEED threshold
    # Free-text, person-specific judgment injected verbatim into the screener prompt.
    # e.g. "Required frontend = reject. Core ML too hardcore; agent/LangGraph work is my strength."
    screening_instructions: str = ""


class ProfileResponse(BaseModel):
    data: ProfileData
    name: str | None = None
    email: EmailStr | None = None
    preferences: Preferences = Field(default_factory=Preferences)


class PreferencesUpdate(BaseModel):
    email: EmailStr
    preferences: Preferences


class InferredPreferences(BaseModel):
    # sensible search defaults derived from the résumé, so a new user isn't starting blank
    titles: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    years_experience: float = 0


class FitAssessment(BaseModel):
    match_score: int = Field(ge=0, le=100)
    reason: str
    missing_skills: list[str]


class TailorResumePayload(BaseModel):
    # identity now comes from the auth token; the router fills this in
    email: EmailStr | None = None
    job_title: str = ""
    company: str = ""
    job_description: str = ""
    job_url: str = ""


class TailoredResumeResult(BaseModel):
    profile: ProfileData
    fit: FitAssessment
