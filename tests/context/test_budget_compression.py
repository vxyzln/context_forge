from uuid import uuid4

import pytest

from context_forge.context import (
    ContextBudgetCompressor,
    ContextPackage,
    ContextUnit,
    ContextUnitType,
)


def make_unit(relevance: float) -> ContextUnit:
    return ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        relevance=relevance,
    )


def make_package(
    *relevances: float,
) -> ContextPackage:
    return ContextPackage(
        task="authentication",
        units=tuple(make_unit(relevance) for relevance in relevances),
    )


def test_budget_compressor_keeps_package_under_budget() -> None:
    package = make_package(0.9, 0.8)

    result = ContextBudgetCompressor().compress(
        package,
        max_units=5,
    )

    assert result == package


def test_budget_compressor_selects_highest_relevance_units() -> None:
    package = make_package(
        0.2,
        0.9,
        0.5,
    )

    result = ContextBudgetCompressor().compress(
        package,
        max_units=2,
    )

    assert len(result.units) == 2
    assert {unit.relevance for unit in result.units} == {
        0.9,
        0.5,
    }


def test_budget_compressor_preserves_original_order() -> None:
    first = make_unit(0.2)
    second = make_unit(0.9)
    third = make_unit(0.8)

    package = ContextPackage(
        task="authentication",
        units=(first, second, third),
    )

    result = ContextBudgetCompressor().compress(
        package,
        max_units=2,
    )

    assert result.units == (second, third)


def test_budget_compressor_preserves_task() -> None:
    package = make_package(
        0.2,
        0.9,
        0.8,
    )

    result = ContextBudgetCompressor().compress(
        package,
        max_units=2,
    )

    assert result.task == "authentication"


def test_budget_compressor_allows_zero_budget() -> None:
    package = make_package(
        0.9,
        0.8,
    )

    result = ContextBudgetCompressor().compress(
        package,
        max_units=0,
    )

    assert result.units == ()


def test_budget_compressor_rejects_negative_budget() -> None:
    package = make_package(0.9)

    with pytest.raises(
        ValueError,
        match="max_units must be non-negative",
    ):
        ContextBudgetCompressor().compress(
            package,
            max_units=-1,
        )


def test_budget_compressor_is_deterministic() -> None:
    first = make_package(
        0.4,
        0.9,
        0.7,
        0.2,
    )

    compressor = ContextBudgetCompressor()

    result_a = compressor.compress(
        first,
        max_units=2,
    )
    result_b = compressor.compress(
        first,
        max_units=2,
    )

    assert result_a == result_b


def test_budget_compressor_tie_breaks_by_original_order() -> None:
    first = make_unit(0.8)
    second = make_unit(0.8)
    third = make_unit(0.8)

    package = ContextPackage(
        task="authentication",
        units=(first, second, third),
    )

    result = ContextBudgetCompressor().compress(
        package,
        max_units=2,
    )

    assert result.units == (first, second)


def test_compress_units_matches_package_compression() -> None:
    package = make_package(
        0.2,
        0.9,
        0.6,
    )

    compressor = ContextBudgetCompressor()

    package_result = compressor.compress(
        package,
        max_units=2,
    )

    units_result = compressor.compress_units(
        list(package.units),
        max_units=2,
    )

    assert units_result == list(package_result.units)
