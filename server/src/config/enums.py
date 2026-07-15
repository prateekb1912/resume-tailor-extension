from enum import Enum


class TailorStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"


class ModelNames(str, Enum):
    GPT_5_5 = "gpt-5.5"
    CLAUDE_SONNET_5 = "claude-sonnet-5"
