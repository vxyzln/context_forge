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
    def __init__(self, max_depth: int = 1) -> None:
        if max_depth < 0:
            raise ValueError("Expansion depth cannot be negative")

        self.max_depth = max_depth

    def expand(
        self,
        project: Project,
        candidates: list[ContextCandidate],
        max_depth: int | None = None,
    ) -> list[ContextExpansion]:
        depth = self.max_depth if max_depth is None else max_depth

        if depth < 0:
            raise ValueError("Expansion depth cannot be negative")

        query = ProjectQuery(project)

        return [
            ContextExpansion(
                candidate=candidate,
                related=tuple(
                    self._expand_related(
                        query,
                        candidate,
                        depth,
                    )
                ),
            )
            for candidate in candidates
        ]

    def _expand_related(
        self,
        query: ProjectQuery,
        candidate: ContextCandidate,
        max_depth: int,
    ) -> list[ContextCandidate]:
        if max_depth == 0:
            return []

        related: list[ContextCandidate] = []
        visited: set[object] = {candidate.entity_id}
        frontier = [candidate.entity_id]

        for _ in range(max_depth):
            next_frontier: list[object] = []

            for entity_id in frontier:
                for related_id in sorted(
                    query.get_related_entity_ids(entity_id),
                    key=str,
                ):
                    if related_id in visited:
                        continue

                    visited.add(related_id)

                    entity = self._get_entity(query, related_id)

                    if entity is None:
                        continue

                    related_candidate = self._to_candidate(entity)

                    if related_candidate is None:
                        continue

                    related.append(related_candidate)
                    next_frontier.append(related_id)

            if not next_frontier:
                break

            frontier = next_frontier

        return related

    @staticmethod
    def _get_entity(
        query: ProjectQuery,
        entity_id: object,
    ) -> object | None:
        for file in query.project.files:
            if file.id == entity_id:
                return file

        for directory in query.project.directories:
            if directory.id == entity_id:
                return directory

        for symbol in query.project.symbols:
            if symbol.id == entity_id:
                return symbol

        return None

    @staticmethod
    def _to_candidate(entity: object) -> ContextCandidate | None:
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
