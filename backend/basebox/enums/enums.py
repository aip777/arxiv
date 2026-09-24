from enum import Enum
from typing import List, Tuple

class ScheduledTaskLogEnum(Enum):
    """Types of ScheduledTaskLogEnum"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

    @classmethod
    def choices(cls) -> List[Tuple[str, str]]:
        """Return Django choices format"""
        return [
            (cls.RUNNING.value, "Running"),
            (cls.SUCCESS.value, "Success"),
            (cls.FAILED.value, "Failed"),
        ]

    @classmethod
    def values(cls) -> List[str]:
        """Return list of enum values"""
        return [enum_type.value for enum_type in cls]