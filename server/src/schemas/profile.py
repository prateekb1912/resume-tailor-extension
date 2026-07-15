from pydantic import BaseModel, ConfigDict, Field, EmailStr


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
    """Structured resume. All fields optional so imperfect LLM output still validates."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    links: list[str] = Field(default_factory=list)
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    data: ProfileData


class ProfileIn(BaseModel):
    email: EmailStr
