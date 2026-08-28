from uuid import uuid4

import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.depth import (
    ContextDepth,
    ContextDepthSelector,
)
from context_forge.context.types import ContextUnitType


def make_candidate(score: float = 0.8) -> ContextCandidate:
    return ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=score,
        source="deterministic_search",
    )


def test_depth_selector_returns_recommended_for_focused_task() -> None:
    candidates = [make_candidate()]

    decision = ContextDepthSelector().select(candidates)

    assert decision.depth == 1
    assert decision.mode == ContextDepth.RECOMMENDED
    assert decision.reason


def test_depth_selector_returns_minimal_when_no_candidates() -> None:
    decision = ContextDepthSelector().select([])

    assert decision.depth == 0
    assert decision.mode == ContextDepth.MINIMAL
    assert "No relevant candidates" in decision.reason


def test_depth_selector_expands_multiple_candidates() -> None:
    candidates = [
        make_candidate(),
        make_candidate(),
    ]

    decision = ContextDepthSelector().select(candidates)

    assert decision.depth == 1
    assert decision.mode == ContextDepth.RECOMMENDED


def test_depth_selector_uses_deep_context_for_many_candidates() -> None:
    candidates = [make_candidate() for _ in range(5)]

    decision = ContextDepthSelector().select(candidates)

    assert decision.depth == 2
    assert decision.mode == ContextDepth.DEEP


def test_depth_selector_uses_deep_context_for_many_high_relevance_candidates() -> None:
    candidates = [
        make_candidate(0.9),
        make_candidate(0.85),
        make_candidate(0.8),
    ]

    decision = ContextDepthSelector().select(candidates)

    assert decision.depth == 2
    assert decision.mode == ContextDepth.DEEP


@pytest.mark.parametrize(
    ("mode", "expected_depth"),
    [
        (ContextDepth.MINIMAL, 0),
        (ContextDepth.RECOMMENDED, 1),
        (ContextDepth.DEEP, 2),
    ],
)
def test_depth_selector_respects_explicit_mode(
    mode: ContextDepth,
    expected_depth: int,
) -> None:
    decision = ContextDepthSelector().select(
        [make_candidate()],
        mode=mode,
    )

    assert decision.depth == expected_depth
    assert decision.mode == mode
    assert mode.value in decision.reason


def test_depth_selector_is_deterministic() -> None:
    candidates = [
        make_candidate(0.9),
        make_candidate(0.7),
    ]

    selector = ContextDepthSelector()

    first = selector.select(candidates)
    second = selector.select(candidates)

    assert first == second
