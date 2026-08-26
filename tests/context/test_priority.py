import pytest

from context_forge.context.priority import ContextPriority


def test_context_priority_stores_score() -> None:
    priority = ContextPriority(
        score=0.85,
        reason="high task relevance",
    )

    assert priority.score == 0.85
    assert priority.reason == "high task relevance"


def test_context_priority_allows_boundary_values() -> None:
    assert ContextPriority(score=0.0).score == 0.0
    assert ContextPriority(score=1.0).score == 1.0


def test_context_priority_rejects_negative_score() -> None:
    with pytest.raises(
        ValueError,
        match="Priority score must be between 0.0 and 1.0",
    ):
        ContextPriority(score=-0.1)


def test_context_priority_rejects_score_above_one() -> None:
    with pytest.raises(
        ValueError,
        match="Priority score must be between 0.0 and 1.0",
    ):
        ContextPriority(score=1.1)


def test_context_priority_is_immutable() -> None:
    priority = ContextPriority(score=0.8)

    with pytest.raises(AttributeError):
        priority.score = 0.9  # type: ignore[misc]
