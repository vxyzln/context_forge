from uuid import uuid4

from context_forge.context import (
    ContextSignal,
    ContextUnitType,
    DeterministicContextCompressor,
    Evidence,
    Fact,
    Inference,
)
from context_forge.context.models import ContextPackage, ContextUnit


def make_unit(
    entity_id,
    *,
    relevance: float = 0.5,
    content: str | None = None,
    signals=(),
    facts=(),
    inferences=(),
):
    return ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        relevance=relevance,
        content=content,
        signals=signals,
        facts=facts,
        inferences=inferences,
    )


def test_compressor_preserves_empty_package() -> None:
    package = ContextPackage(task="authentication")

    result = DeterministicContextCompressor().compress(package)

    assert result == package


def test_compressor_preserves_unique_units() -> None:
    first_id = uuid4()
    second_id = uuid4()

    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(first_id, relevance=0.8),
            make_unit(second_id, relevance=0.6),
        ),
    )

    result = DeterministicContextCompressor().compress(package)

    assert result.units == package.units


def test_compressor_removes_duplicate_units() -> None:
    entity_id = uuid4()

    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(entity_id, relevance=0.8),
            make_unit(entity_id, relevance=0.6),
        ),
    )

    result = DeterministicContextCompressor().compress(package)

    assert len(result.units) == 1
    assert result.units[0].entity_id == entity_id


def test_compressor_keeps_highest_relevance() -> None:
    entity_id = uuid4()

    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(entity_id, relevance=0.4),
            make_unit(entity_id, relevance=0.9),
        ),
    )

    result = DeterministicContextCompressor().compress(package)

    assert result.units[0].relevance == 0.9


def test_compressor_merges_unique_signals() -> None:
    entity_id = uuid4()

    first = make_unit(
        entity_id,
        signals=(ContextSignal(name="importance", value=0.8),),
    )
    second = make_unit(
        entity_id,
        signals=(ContextSignal(name="dependency", value=0.7),),
    )

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(first, second),
        )
    )

    assert result.units[0].signals == (
        ContextSignal(name="importance", value=0.8),
        ContextSignal(name="dependency", value=0.7),
    )


def test_compressor_deduplicates_signals() -> None:
    entity_id = uuid4()

    signal = ContextSignal(name="importance", value=0.8)

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(
                make_unit(entity_id, signals=(signal,)),
                make_unit(entity_id, signals=(signal,)),
            ),
        )
    )

    assert result.units[0].signals == (signal,)


def test_compressor_merges_unique_facts() -> None:
    entity_id = uuid4()

    first = make_unit(
        entity_id,
        facts=(Fact(fact_type="language", value="python"),),
    )
    second = make_unit(
        entity_id,
        facts=(Fact(fact_type="size", value="128"),),
    )

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(first, second),
        )
    )

    assert result.units[0].facts == (
        Fact(fact_type="language", value="python"),
        Fact(fact_type="size", value="128"),
    )


def test_compressor_deduplicates_facts() -> None:
    entity_id = uuid4()

    fact = Fact(fact_type="language", value="python")

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(
                make_unit(entity_id, facts=(fact,)),
                make_unit(entity_id, facts=(fact,)),
            ),
        )
    )

    assert result.units[0].facts == (fact,)


def test_compressor_merges_unique_inferences() -> None:
    entity_id = uuid4()

    first = make_unit(
        entity_id,
        inferences=(
            Inference(
                claim="likely authentication code",
                confidence=0.8,
            ),
        ),
    )
    second = make_unit(
        entity_id,
        inferences=(
            Inference(
                claim="security-sensitive",
                confidence=0.7,
            ),
        ),
    )

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(first, second),
        )
    )

    assert result.units[0].inferences == (
        Inference(
            claim="likely authentication code",
            confidence=0.8,
        ),
        Inference(
            claim="security-sensitive",
            confidence=0.7,
        ),
    )


def test_compressor_deduplicates_inferences() -> None:
    entity_id = uuid4()

    inference = Inference(
        claim="likely authentication code",
        confidence=0.8,
    )

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(
                make_unit(entity_id, inferences=(inference,)),
                make_unit(entity_id, inferences=(inference,)),
            ),
        )
    )

    assert result.units[0].inferences == (inference,)


def test_compressor_merges_duplicate_fact_evidence() -> None:
    entity_id = uuid4()
    source_id = uuid4()

    first_evidence = Evidence(
        source_id=source_id,
        description="scanner",
    )
    second_evidence = Evidence(
        source_id=uuid4(),
        description="parser",
    )

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(
                make_unit(
                    entity_id,
                    facts=(
                        Fact(
                            fact_type="language",
                            value="python",
                            evidence=(first_evidence,),
                        ),
                    ),
                ),
                make_unit(
                    entity_id,
                    facts=(
                        Fact(
                            fact_type="language",
                            value="python",
                            evidence=(second_evidence,),
                        ),
                    ),
                ),
            ),
        )
    )

    assert result.units[0].facts[0].evidence == (
        first_evidence,
        second_evidence,
    )


def test_compressor_deduplicates_evidence() -> None:
    entity_id = uuid4()
    evidence = Evidence(
        source_id=uuid4(),
        description="scanner",
    )

    result = DeterministicContextCompressor().compress(
        ContextPackage(
            task="authentication",
            units=(
                make_unit(
                    entity_id,
                    facts=(
                        Fact(
                            fact_type="language",
                            value="python",
                            evidence=(evidence,),
                        ),
                    ),
                ),
                make_unit(
                    entity_id,
                    facts=(
                        Fact(
                            fact_type="language",
                            value="python",
                            evidence=(evidence,),
                        ),
                    ),
                ),
            ),
        )
    )

    assert result.units[0].facts[0].evidence == (evidence,)


def test_compressor_preserves_task() -> None:
    package = ContextPackage(task="  authentication  ")

    result = DeterministicContextCompressor().compress(package)

    assert result.task == package.task


def test_compressor_is_deterministic() -> None:
    entity_id = uuid4()

    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(
                entity_id,
                relevance=0.4,
                facts=(Fact(fact_type="language", value="python"),),
            ),
            make_unit(
                entity_id,
                relevance=0.9,
                facts=(Fact(fact_type="size", value="128"),),
            ),
        ),
    )

    compressor = DeterministicContextCompressor()

    first = compressor.compress(package)
    second = compressor.compress(package)

    assert first == second

def test_compressor_preserves_content() -> None:
    entity_id = uuid4()
    source = "def authenticate():\n    return True\n"

    package = ContextPackage(
        task="authentication",
        units=(make_unit(entity_id, content=source),),
    )

    result = DeterministicContextCompressor().compress(package)

    assert result.units[0].content == source

def test_compressor_preserves_content_when_merging_duplicates() -> None:
    entity_id = uuid4()
    source = "def authenticate():\n    return True\n"

    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(entity_id, relevance=0.8, content=source),
            make_unit(entity_id, relevance=0.6, content=source),
        ),
    )

    result = DeterministicContextCompressor().compress(package)

    assert len(result.units) == 1
    assert result.units[0].content == source