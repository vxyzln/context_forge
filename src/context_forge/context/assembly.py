from context_forge.context.models import ContextPackage
from context_forge.context.priority_ordering import ContextPriorityOrdering


class ContextAssembler:
    """Assemble the final deterministic context package."""

    def __init__(
        self,
        ordering: ContextPriorityOrdering,
    ) -> None:
        self.ordering = ordering

    def assemble(
        self,
        package: ContextPackage,
    ) -> ContextPackage:
        ordered_units = self.ordering.order(list(package.units))

        return ContextPackage(
            task=package.task,
            units=tuple(ordered_units),
        )
