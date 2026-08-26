from uuid import UUID

from context_forge.context import (
    ContextAssembler,
    ContextPackage,
    ContextPriority,
    ContextPriorityOrdering,
    ContextUnit,
    ContextUnitType,
)


class StubPrioritizer:
    def __init__(self, scores: dict[UUID, float]) -> None:
        self.scores = scores

    def prioritize(self, unit: ContextUnit) -> ContextPriority:
        return ContextPriority(score=self.scores[unit.entity_id])


def make_unit(
    entity_id: UUID,
    unit_type: ContextUnitType = ContextUnitType.FILE,
) -> ContextUnit:
    return ContextUnit(
        entity_id=entity_id,
        unit_type=unit_type,
        relevance=0.5,
    )


def test_assembler_orders_units_by_priority() -> None:
    low_id = UUID("00000000-0000-0000-0000-000000000001")
    high_id = UUID("00000000-0000-0000-0000-000000000002")

    low = make_unit(low_id)
    high = make_unit(high_id)

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                low_id: 0.2,
                high_id: 0.9,
            },
        ),
    )

    package = ContextPackage(
        task="authentication",
        units=(low, high),
    )

    result = ContextAssembler(ordering).assemble(package)

    assert result.task == "authentication"
    assert result.units == (high, low)


def test_assembler_preserves_task() -> None:
    package = ContextPackage(
        task="find authentication",
        units=(),
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer({}),
    )

    result = ContextAssembler(ordering).assemble(package)

    assert result.task == "find authentication"


def test_assembler_preserves_all_units() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")
    third_id = UUID("00000000-0000-0000-0000-000000000003")

    units = (
        make_unit(first_id),
        make_unit(second_id),
        make_unit(third_id),
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                first_id: 0.3,
                second_id: 0.9,
                third_id: 0.6,
            },
        ),
    )

    package = ContextPackage(
        task="authentication",
        units=units,
    )

    result = ContextAssembler(ordering).assemble(package)

    assert {unit.entity_id for unit in result.units} == {
        first_id,
        second_id,
        third_id,
    }


def test_assembler_preserves_unit_content() -> None:
    entity_id = UUID("00000000-0000-0000-0000-000000000001")

    unit = ContextUnit(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        relevance=0.8,
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer({entity_id: 0.9}),
    )

    package = ContextPackage(
        task="authentication",
        units=(unit,),
    )

    result = ContextAssembler(ordering).assemble(package)

    assert result.units[0] == unit


def test_assembler_is_deterministic() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    first = make_unit(first_id)
    second = make_unit(second_id)

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                first_id: 0.7,
                second_id: 0.7,
            },
        ),
    )

    package_a = ContextPackage(
        task="authentication",
        units=(second, first),
    )

    package_b = ContextPackage(
        task="authentication",
        units=(first, second),
    )

    assembler = ContextAssembler(ordering)

    result_a = assembler.assemble(package_a)
    result_b = assembler.assemble(package_b)

    assert result_a == result_b


def test_assembler_preserves_empty_package() -> None:
    package = ContextPackage(
        task="authentication",
        units=(),
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer({}),
    )

    result = ContextAssembler(ordering).assemble(package)

    assert result == package
