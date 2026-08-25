from uuid import uuid4

from context_forge.context import (
    ContextSignal,
    ContextUnit,
    ContextUnitMerger,
    ContextUnitType,
    Evidence,
    Fact,
    Inference,
)


def test_merger_deduplicates_units() -> None:
    entity_id = uuid4()

    units = [
        ContextUnit(
            entity_id=entity_id,
            unit_type=ContextUnitType.FILE,
            relevance=0.5,
        ),
        ContextUnit(
            entity_id=entity_id,
            unit_type=ContextUnitType.FILE,
            relevance=0.9,
        ),
    ]

    result = ContextUnitMerger().merge(units)

    assert len(result) == 1
    assert result[0].relevance == 0.9


def test_merger_preserves_facts() -> None:
    entity_id = uuid4()

    first_evidence = Evidence(
        source_id=entity_id,
        description="path metadata",
    )
    second_evidence = Evidence(
        source_id=entity_id,
        description="extension metadata",
    )

    first = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        facts=(
            Fact(
                fact_type="file_path",
                value="src/auth.py",
                evidence=(first_evidence,),
            ),
        ),
    )

    second = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        facts=(
            Fact(
                fact_type="extension",
                value=".py",
                evidence=(second_evidence,),
            ),
        ),
    )

    result = ContextUnitMerger().merge([first, second])

    assert len(result) == 1
    assert len(result[0].facts) == 2
    assert result[0].facts[0].evidence
    assert result[0].facts[1].evidence


def test_merger_preserves_signal_evidence() -> None:
    entity_id = uuid4()

    evidence_a = Evidence(
        source_id=entity_id,
        description="signal source A",
    )
    evidence_b = Evidence(
        source_id=entity_id,
        description="signal source B",
    )

    first = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        signals=(
            ContextSignal(
                name="relevance",
                value=0.8,
                evidence=(evidence_a,),
            ),
        ),
    )

    second = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        signals=(
            ContextSignal(
                name="relevance",
                value=0.8,
                evidence=(evidence_b,),
            ),
        ),
    )

    result = ContextUnitMerger().merge([first, second])

    assert len(result) == 1
    assert len(result[0].signals) == 1
    assert len(result[0].signals[0].evidence) == 2


def test_merger_preserves_inference_evidence() -> None:
    entity_id = uuid4()

    evidence_a = Evidence(
        source_id=entity_id,
        description="source A",
    )
    evidence_b = Evidence(
        source_id=entity_id,
        description="source B",
    )

    first = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        inferences=(
            Inference(
                claim="authentication related",
                confidence=0.7,
                evidence=(evidence_a,),
            ),
        ),
    )

    second = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        inferences=(
            Inference(
                claim="authentication related",
                confidence=0.9,
                evidence=(evidence_b,),
            ),
        ),
    )

    result = ContextUnitMerger().merge([first, second])

    assert len(result) == 1
    assert result[0].inferences[0].confidence == 0.9
    assert len(result[0].inferences[0].evidence) == 2


def test_merger_keeps_conflicting_facts() -> None:
    entity_id = uuid4()

    first = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        facts=(
            Fact(
                fact_type="extension",
                value=".py",
            ),
        ),
    )

    second = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        facts=(
            Fact(
                fact_type="extension",
                value=".js",
            ),
        ),
    )

    result = ContextUnitMerger().merge([first, second])

    assert len(result) == 1
    assert len(result[0].facts) == 2
    assert {fact.value for fact in result[0].facts} == {".py", ".js"}


def test_merger_is_deterministic() -> None:
    entity_id = uuid4()

    units = [
        ContextUnit(
            entity_id=entity_id,
            unit_type=ContextUnitType.FILE,
            relevance=0.4,
            facts=(
                Fact(
                    fact_type="name",
                    value="auth.py",
                ),
            ),
        ),
        ContextUnit(
            entity_id=entity_id,
            unit_type=ContextUnitType.FILE,
            relevance=0.8,
            facts=(
                Fact(
                    fact_type="extension",
                    value=".py",
                ),
            ),
        ),
    ]

    merger = ContextUnitMerger()

    assert merger.merge(units) == merger.merge(units)
