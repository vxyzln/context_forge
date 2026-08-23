from uuid import uuid4

import pytest

from context_forge.context.models import (
    ContextPackage,
    ContextSignal,
    ContextUnit,
    Evidence,
    Fact,
    Inference,
)


def test_evidence_stores_source_and_description() -> None:
    source_id = uuid4()

    evidence = Evidence(
        source_id=source_id,
        description="File imports database module",
    )

    assert evidence.source_id == source_id
    assert evidence.description == "File imports database module"


def test_context_signal_stores_evidence() -> None:
    source_id = uuid4()

    signal = ContextSignal(
        name="dependency_relevance",
        value=0.8,
        evidence=(
            Evidence(
                source_id=source_id,
                description="Imported by multiple files",
            ),
        ),
    )

    assert signal.name == "dependency_relevance"
    assert signal.value == 0.8
    assert len(signal.evidence) == 1


def test_context_unit_defaults_to_zero_relevance() -> None:
    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type="file",
    )

    assert unit.relevance == 0.0
    assert unit.signals == ()


def test_context_package_stores_task_and_units() -> None:
    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type="file",
        relevance=0.9,
    )

    package = ContextPackage(
        task="Fix authentication",
        units=(unit,),
    )

    assert package.task == "Fix authentication"
    assert package.units == (unit,)


def test_fact_stores_evidence() -> None:
    source_id = uuid4()

    fact = Fact(
        fact_type="imports",
        value="database.py",
        evidence=(
            Evidence(
                source_id=source_id,
                description="Import discovered by parser",
            ),
        ),
    )

    assert fact.fact_type == "imports"
    assert fact.value == "database.py"
    assert len(fact.evidence) == 1


def test_inference_stores_confidence() -> None:
    inference = Inference(
        claim="This module appears to handle authentication.",
        confidence=0.85,
    )

    assert inference.confidence == 0.85


def test_inference_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        Inference(
            claim="Invalid confidence",
            confidence=1.5,
        )


def test_context_unit_can_store_facts_and_inferences() -> None:
    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type="file",
        facts=(
            Fact(
                fact_type="language",
                value="Python",
            ),
        ),
        inferences=(
            Inference(
                claim="Likely application code",
                confidence=0.8,
            ),
        ),
    )

    assert len(unit.facts) == 1
    assert len(unit.inferences) == 1
