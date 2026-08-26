from context_forge.context.models import ContextUnit
from context_forge.context.prioritization import DeterministicPrioritizer
from context_forge.context.priority import ContextPriority


class ContextPriorityOrdering:
    """Order context units deterministically by calculated prioroity"""

    def __init__(
        self,
        prioritizer: DeterministicPrioritizer,
    ) -> None:
        self.prioritizer = prioritizer

    def order(
        self,
        units: list[ContextUnit],
    ) -> list[ContextUnit]:
        priorities = {
            unit.entity_id: self.prioritizer.prioritize(unit) for unit in units
        }

        return sorted(
            units,
            key=lambda unit: self._sort_key(
                unit,
                priorities[unit.entity_id],
            ),
        )

    def _sort_key(
        self,
        unit: ContextUnit,
        priority: ContextPriority,
    ) -> tuple[float, str, str]:
        return (-priority.score, unit.unit_type.value, str(unit.entity_id))
