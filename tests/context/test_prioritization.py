from uuid import uuid4

from context_forge.context.models import (
    ContextSignal,
    ContextUnit,
    Evidence,
    Fact,
    Inference,
)
from context_forge.context.prioritization import DeterministicPrioritizer
from context_forge.context.priority import ContextPriority
from context_forge.context.types import ContextUnitType


def make_unit(
    *,
    relevance: float = 0.8,
    unit_type: ContextUnitType = ContextUnitType.FILE,
) -> ContextUnit:
    return ContextUnit(
        entity_id=uuid4(),
        unit_type=unit_type,
        relevance=relevance,
    )


def test_prioritizer_returns_context_priority() -> None:
    result = DeterministicPrioritizer().prioritize(
        make_unit(),
    )

    assert isinstance(result, ContextPriority)
    assert 0.0 <= result.score <= 1.0


def test_prioritizer_prefers_higher_relevance() -> None:
    prioritizer = DeterministicPrioritizer()

    low = prioritizer.prioritize(
        make_unit(relevance=0.2),
    )
    high = prioritizer.prioritize(
        make_unit(relevance=0.9),
    )

    assert high.score > low.score


def test_prioritizer_uses_unit_type() -> None:
    prioritizer = DeterministicPrioritizer()

    symbol = prioritizer.prioritize(
        make_unit(
            relevance=0.7,
            unit_type=ContextUnitType.SYMBOL,
        ),
    )

    directory = prioritizer.prioritize(
        make_unit(
            relevance=0.7,
            unit_type=ContextUnitType.DIRECTORY,
        ),
    )

    assert symbol.score > directory.score


def test_prioritizer_rewards_evidence() -> None:
    prioritizer = DeterministicPrioritizer()

    without_evidence = make_unit()

    evidence = Evidence(
        source_id=without_evidence.entity_id,
        description="direct source",
    )

    with_evidence = ContextUnit(
        entity_id=without_evidence.entity_id,
        unit_type=ContextUnitType.FILE,
        relevance=without_evidence.relevance,
        signals=(
            ContextSignal(
                name="relevance",
                value=0.8,
                evidence=(evidence,),
            ),
        ),
    )

    first = prioritizer.prioritize(without_evidence)
    second = prioritizer.prioritize(with_evidence)

    assert second.score > first.score


def test_prioritizer_counts_all_evidence_sources() -> None:
    unit = make_unit()

    evidence = Evidence(
        source_id=unit.entity_id,
        description="source",
    )

    enriched = ContextUnit(
        entity_id=unit.entity_id,
        unit_type=unit.unit_type,
        relevance=unit.relevance,
        signals=(
            ContextSignal(
                name="signal",
                value=0.5,
                evidence=(evidence,),
            ),
        ),
        facts=(
            Fact(
                fact_type="metadata",
                value="known",
                evidence=(evidence,),
            ),
        ),
        inferences=(
            Inference(
                claim="likely relevant",
                confidence=0.8,
                evidence=(evidence,),
            ),
        ),
    )

    result = DeterministicPrioritizer().prioritize(enriched)

    assert "evidence_count=3" in result.reason


def test_prioritizer_is_deterministic() -> None:
    entity_id = uuid4()

    unit = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        relevance=0.8,
    )

    prioritizer = DeterministicPrioritizer()

    first = prioritizer.prioritize(unit)
    second = prioritizer.prioritize(unit)

    assert first == second


def test_prioritizer_reason_is_explainable() -> None:
    result = DeterministicPrioritizer().prioritize(
        make_unit(relevance=0.75),
    )

    assert "relevance=0.750" in result.reason
    assert "type_weight=" in result.reason
    assert "evidence_count=0" in result.reason


def test_prioritizer_clamps_score_to_valid_range() -> None:
    unit = make_unit(relevance=1.0)

    result = DeterministicPrioritizer().prioritize(unit)

    assert 0.0 <= result.score <= 1.0
