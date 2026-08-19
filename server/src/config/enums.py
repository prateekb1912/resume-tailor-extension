from enum import Enum


class TailorStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"


class ModelNames(str, Enum):
    GPT_5_5 = "gpt-5.5"
    CLAUDE_SONNET_5 = "claude-sonnet-5"


class WorkType(str, Enum):
    REMOTE = "remote"
    ONSITE = "onsite"
    HYBRID = "hybrid"


class JobSource(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKABLE = "workable"
    LINKEDIN = "linkedin"


class ApplicationStatus(str, Enum):
    SKIPPED = "skipped"   # auto: below the user's min fit score
    NEW = "new"
    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
