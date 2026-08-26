from uuid import UUID, uuid4

from context_forge.context.models import ContextUnit
from context_forge.context.prioritization import DeterministicPrioritizer
from context_forge.context.priority import ContextPriority
from context_forge.context.priority_ordering import ContextPriorityOrdering
from context_forge.context.types import ContextUnitType


class StubPrioritizer(DeterministicPrioritizer):
    def __init__(self, priorities: dict[UUID, float]) -> None:
        self.priorities = priorities

    def prioritize(self, unit: ContextUnit) -> ContextPriority:
        return ContextPriority(
            score=self.priorities[unit.entity_id],
            reason="test",
        )


def make_unit(
    entity_id: UUID,
    unit_type: ContextUnitType,
    relevance: float = 0.5,
) -> ContextUnit:
    return ContextUnit(
        entity_id=entity_id,
        unit_type=unit_type,
        relevance=relevance,
    )


def test_order_places_highest_priority_first() -> None:
    low_id = uuid4()
    high_id = uuid4()

    low = make_unit(
        low_id,
        ContextUnitType.FILE,
    )
    high = make_unit(
        high_id,
        ContextUnitType.FILE,
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                low_id: 0.2,
                high_id: 0.9,
            },
        ),
    )

    result = ordering.order([low, high])

    assert result == [high, low]


def test_order_is_deterministic() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    first = make_unit(
        first_id,
        ContextUnitType.FILE,
    )
    second = make_unit(
        second_id,
        ContextUnitType.FILE,
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                first_id: 0.8,
                second_id: 0.8,
            },
        ),
    )

    result_a = ordering.order([second, first])
    result_b = ordering.order([first, second])

    assert result_a == result_b
    assert result_a == [first, second]


def test_order_uses_unit_type_as_first_tiebreaker() -> None:
    file_id = UUID("00000000-0000-0000-0000-000000000002")
    symbol_id = UUID("00000000-0000-0000-0000-000000000001")

    file = make_unit(
        file_id,
        ContextUnitType.FILE,
    )
    symbol = make_unit(
        symbol_id,
        ContextUnitType.SYMBOL,
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                file_id: 0.8,
                symbol_id: 0.8,
            },
        ),
    )

    result = ordering.order([symbol, file])

    assert result == [file, symbol]


def test_order_uses_entity_id_as_final_tiebreaker() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    first = make_unit(
        first_id,
        ContextUnitType.FILE,
    )
    second = make_unit(
        second_id,
        ContextUnitType.FILE,
    )

    ordering = ContextPriorityOrdering(
        StubPrioritizer(
            {
                first_id: 0.8,
                second_id: 0.8,
            },
        ),
    )

    result = ordering.order([second, first])

    assert result == [first, second]


def test_order_preserves_all_units() -> None:
    units = [
        make_unit(uuid4(), ContextUnitType.FILE),
        make_unit(uuid4(), ContextUnitType.SYMBOL),
        make_unit(uuid4(), ContextUnitType.DIRECTORY),
    ]

    ordering = ContextPriorityOrdering(
        DeterministicPrioritizer(),
    )

    result = ordering.order(units)

    assert len(result) == len(units)
    assert set(result) == set(units)


def test_order_handles_empty_input() -> None:
    ordering = ContextPriorityOrdering(
        DeterministicPrioritizer(),
    )

    assert ordering.order([]) == []
