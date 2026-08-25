from context_forge.context.models import ContextPackage, ContextUnit


class ContextBudgetCompressor:
    """Deterministically reduces a context package to a unit budget."""

    def compress(
        self,
        package: ContextPackage,
        max_units: int,
    ) -> ContextPackage:
        if max_units < 0:
            raise ValueError("max_units must be non-negative")

        if len(package.units) <= max_units:
            return package

        ranked_units = sorted(
            enumerate(package.units),
            key=lambda item: (
                -item[1].relevance,
                item[0],
            ),
        )

        selected = ranked_units[:max_units]

        selected.sort(key=lambda item: item[0])

        return ContextPackage(
            task=package.task,
            units=tuple(unit for _, unit in selected),
        )

    def compress_units(
        self,
        units: list[ContextUnit],
        max_units: int,
    ) -> list[ContextUnit]:
        if max_units < 0:
            raise ValueError("max_units must be non-negative")

        if len(units) <= max_units:
            return list(units)

        ranked_units = sorted(
            enumerate(units),
            key=lambda item: (
                -item[1].relevance,
                item[0],
            ),
        )

        selected = ranked_units[:max_units]
        selected.sort(key=lambda item: item[0])

        return [unit for _, unit in selected]
