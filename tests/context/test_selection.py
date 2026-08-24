import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.selection import ContextSelector
from context_forge.context.types import ContextUnitType


def make_candidate(score: float) -> ContextCandidate:
    return ContextCandidate(
        entity_id=object(),
        unit_type=ContextUnitType.FILE,
        score=score,
        source="test",
    )


def test_selector_returns_all_candidates_without_limit() -> None:
    candidates = [make_candidate(0.9), make_candidate(0.7)]

    result = ContextSelector().select(candidates)

    assert result == candidates


def test_selector_limits_number_of_candidates() -> None:
    candidates = [
        make_candidate(0.9),
        make_candidate(0.7),
        make_candidate(0.5),
    ]

    result = ContextSelector().select(candidates, limit=2)

    assert result == candidates[:2]


def test_selector_rejects_negative_limit() -> None:
    with pytest.raises(ValueError, match="negative"):
        ContextSelector().select([], limit=-1)
