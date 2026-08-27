from uuid import uuid4

from context_forge.context import (
    ContextBudgetCompressor,
    ContextCompressionPipeline,
    ContextPackage,
    ContextUnit,
    ContextUnitType,
    DeterministicContextCompressor,
)


def make_unit(relevance: float) -> ContextUnit:
    return ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        relevance=relevance,
    )


def make_pipeline() -> ContextCompressionPipeline:
    return ContextCompressionPipeline(
        compressor=DeterministicContextCompressor(),
        budget_compressor=ContextBudgetCompressor(),
    )


def test_compression_pipeline_runs_all_stages() -> None:
    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(0.2),
            make_unit(0.9),
            make_unit(0.7),
        ),
    )

    result = make_pipeline().compress(
        package,
        max_units=2,
    )

    assert result.task == "authentication"
    assert len(result.units) == 2


def test_compression_pipeline_preserves_highest_relevance() -> None:
    package = ContextPackage(
        task="authentication",
        units=(
            make_unit(0.2),
            make_unit(0.9),
            make_unit(0.7),
        ),
    )

    result = make_pipeline().compress(
        package,
        max_units=2,
    )

    assert {unit.relevance for unit in result.units} == {
        0.9,
        0.7,
    }


def test_compression_pipeline_preserves_empty_package() -> None:
    package = ContextPackage(
        task="authentication",
        units=(),
    )

    result = make_pipeline().compress(
        package,
        max_units=2,
    )

    assert result == package


def test_compression_pipeline_is_deterministic() -> None:
    entity_id = uuid4()

    package = ContextPackage(
        task="authentication",
        units=(
            ContextUnit(
                entity_id=entity_id,
                unit_type=ContextUnitType.FILE,
                relevance=0.5,
            ),
            make_unit(0.9),
            make_unit(0.7),
        ),
    )

    pipeline = make_pipeline()

    first = pipeline.compress(package, max_units=2)
    second = pipeline.compress(package, max_units=2)

    assert first == second
