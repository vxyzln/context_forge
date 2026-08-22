from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class SearchResultType(StrEnum):
    FILE = "file"
    SYMBOL = "symbol"


@dataclass(frozen=True)
class SearchResult:
    result_type: SearchResultType
    entity_id: UUID
    name: str
    path: str | None = None
    qualified_name: str | None = None
    score: float = 0.0
