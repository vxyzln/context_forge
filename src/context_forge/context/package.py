from context_forge.context.expansion import ContextExpansion
from context_forge.context.models import ContextPackage, ContextUnit


class ContextPackageBuilder:
    def build(
        self,
        task: str,
        expansions: list[ContextExpansion],
    ) -> ContextPackage:
        units: list[ContextUnit] = []

        for expansion in expansions:
            candidate = expansion.candidate

            units.append(
                ContextUnit(
                    entity_id=candidate.entity_id,
                    unit_type=candidate.unit_type,
                    relevance=candidate.score,
                )
            )

            for related in expansion.related:
                units.append(
                    ContextUnit(
                        entity_id=related.entity_id,
                        unit_type=related.unit_type,
                        relevance=related.score,
                    )
                )

        return ContextPackage(
            task=task.strip(),
            units=tuple(units),
        )
