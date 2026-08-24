from uuid import uuid4

from context_forge.context.candidate import ContextCandidate
from context_forge.context.types import ContextUnitType
from context_forge.query.result import SearchResult, SearchResultType


def test_candidate_can_be_created_from_search_result() -> None:
    entity_id = uuid4()

    result = SearchResult(
        result_type=SearchResultType.FILE,
        entity_id=entity_id,
        name="auth.py",
        path="src/auth.py",
        score=0.9,
    )

    candidate = ContextCandidate.from_search_result(result)

    assert candidate.entity_id == entity_id
    assert candidate.unit_type == ContextUnitType.FILE
    assert candidate.score == 0.9
    assert candidate.source == "deterministic_search"
