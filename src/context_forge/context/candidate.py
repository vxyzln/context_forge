from dataclasses import dataclass

from context_forge.context.types import ContextUnitType
from context_forge.query.result import SearchResult


@dataclass(frozen=True)
class ContextCandidate:
    entity_id: object
    unit_type: ContextUnitType
    score: float
    source: str
    reason: str | None = None

    @classmethod
    def from_search_result(
        cls,
        result: SearchResult,
    ) -> "ContextCandidate":
        return cls(
            entity_id=result.entity_id,
            unit_type=ContextUnitType(result.result_type.value),
            score=result.score,
            source="deterministic_search",
            reason=result.reason,
        )
