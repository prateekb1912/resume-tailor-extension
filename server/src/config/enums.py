from enum import Enum


class TailorStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"
