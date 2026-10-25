from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RawRecord:
    line_number: int
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class CleanedRecord:
    record_id: str
    user_id: str
    amount: float
    category: str
    timestamp: str
