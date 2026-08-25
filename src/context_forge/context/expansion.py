from dataclasses import dataclass

from context_forge.context.candidate import ContextCandidate
from context_forge.context.types import ContextUnitType
from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.query.project import ProjectQuery


@dataclass(frozen=True)
class ContextExpansion:
    candidate: ContextCandidate
    related: tuple[ContextCandidate, ...] = ()


class GraphExpander:
    def expand(self, project: Project, candidates: list[ContextExpansion]):
        query = ProjectQuery(project)
        expansions = []

        for candidate in candidates:
            related: list[ContextCandidate] = []

            for entity in query.get_related_entities(candidate.entity_id):
                related_candidate = self._to_candidate(entity)

                if related_candidate is not None:
                    related.append(related_candidate)

            expansions.append(
                ContextExpansion(
                    candidate=candidate,
                    related=tuple(related),
                )
            )
        return expansions

    def _to_candidate(self, entity: object) -> ContextCandidate | None:
        if isinstance(entity, File):
            unit_type = ContextUnitType.FILE
        elif isinstance(entity, Directory):
            unit_type = ContextUnitType.DIRECTORY
        elif isinstance(entity, Symbol):
            unit_type = ContextUnitType.SYMBOL
        else:
            return None

        return ContextCandidate(
            entity_id=entity.id,
            unit_type=unit_type,
            score=0.0,
            source="graph_expansion",
        )
