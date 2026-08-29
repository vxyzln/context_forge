from uuid import uuid4

import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.ranking import DeterministicRanker
from context_forge.context.signals import RelevanceSignals
from context_forge.context.types import ContextUnitType


def test_ranker_adds_relevance_signals() -> None:
    candidate = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )

    signals = RelevanceSignals(lexical=0.2)

    score = DeterministicRanker().score(candidate, signals)

    assert score == pytest.approx(0.6)


def test_ranker_caps_score_at_one() -> None:
    candidate = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.9,
        source="deterministic_search",
    )

    signals = RelevanceSignals(lexical=0.5)

    score = DeterministicRanker().score(candidate, signals)

    assert score == 1.0


def test_ranker_orders_highest_score_first() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
    )

    signals = {
        first.entity_id: RelevanceSignals(),
        second.entity_id: RelevanceSignals(),
    }

    results = DeterministicRanker().rank(
        [first, second],
        signals,
    )

    assert results[0].entity_id == second.entity_id
    assert results[1].entity_id == first.entity_id


def test_ranker_is_deterministic_for_equal_scores() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.5,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.5,
        source="deterministic_search",
    )

    ranker = DeterministicRanker()

    first_result = ranker.rank([first, second], {})
    second_result = ranker.rank([second, first], {})

    assert [item.entity_id for item in first_result] == [
        item.entity_id for item in second_result
    ]


def test_ranker_uses_task_target_relevance() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )

    signals = {
        first.entity_id: RelevanceSignals(task=1.0),
        second.entity_id: RelevanceSignals(),
    }

    results = DeterministicRanker().rank(
        [first, second],
        signals,
    )

    assert results[0].entity_id == first.entity_id
    assert results[0].score == 1.0
    assert results[1].entity_id == second.entity_id


def test_ranker_uses_task_concept_relevance() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )

    signals = {
        first.entity_id: RelevanceSignals(task=0.5),
        second.entity_id: RelevanceSignals(),
    }

    results = DeterministicRanker().rank(
        [first, second],
        signals,
    )

    assert results[0].entity_id == first.entity_id
    assert results[0].score == pytest.approx(0.9)
    assert results[1].entity_id == second.entity_id


def test_ranker_preserves_behavior_without_task_signals() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.4,
        source="deterministic_search",
    )

    results = DeterministicRanker().rank(
        [first, second],
        {},
    )

    assert results[0].entity_id == first.entity_id
    assert results[0].score == pytest.approx(0.8)
    assert results[1].entity_id == second.entity_id
    assert results[1].score == pytest.approx(0.4)


def test_ranker_remains_deterministic_with_task_signals() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.5,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.5,
        source="deterministic_search",
    )

    signals = {
        first.entity_id: RelevanceSignals(task=0.2),
        second.entity_id: RelevanceSignals(task=0.2),
    }

    ranker = DeterministicRanker()

    first_result = ranker.rank(
        [first, second],
        signals,
    )
    second_result = ranker.rank(
        [second, first],
        signals,
    )

    assert [item.entity_id for item in first_result] == [
        item.entity_id for item in second_result
    ]
