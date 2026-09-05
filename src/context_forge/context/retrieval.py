from context_forge.context.candidate import ContextCandidate
from context_forge.context.types import ContextUnitType
from context_forge.models.project import Project
from context_forge.query.project import ProjectQuery


class RelationshipCandidateRetriever:
    def __init__(
        self,
        relationship_types: set[str] | None = None,
        max_depth: int = 1,
        max_candidates: int | None = None,
    ) -> None:
        if max_depth < 1:
            raise ValueError("Relationship expansion depth must be positive")

        if max_candidates is not None and max_candidates < 1:
            raise ValueError("Maximum expanded candidate count must be positive")

        self.relationship_types = relationship_types
        self.max_depth = max_depth
        self.max_candidates = max_candidates

    def expand(
        self,
        project: Project,
        candidates: list[ContextCandidate],
    ) -> list[ContextCandidate]:
        query = ProjectQuery(project)
        expanded = list(candidates)
        existing = {
            (candidate.entity_id, candidate.unit_type) for candidate in candidates
        }

        if self.max_candidates is not None and len(expanded) >= self.max_candidates:
            return expanded[: self.max_candidates]

        for candidate in candidates:
            related_ids = query.traverse(
                candidate.entity_id,
                max_depth=self.max_depth,
                relationship_types=self.relationship_types,
            )

            for entity_id in related_ids:
                entity = self._get_entity(project, entity_id)

                if entity is None:
                    continue

                unit_type = self._entity_type(entity)
                key = (entity_id, unit_type)

                if key in existing:
                    continue

                expanded.append(
                    ContextCandidate(
                        entity_id=entity_id,
                        unit_type=unit_type,
                        score=candidate.score,
                        source="relationship_expansion",
                        reason="Direct repository relationship",
                    )
                )
                existing.add(key)

                if (
                    self.max_candidates is not None
                    and len(expanded) >= self.max_candidates
                ):
                    return expanded

        return expanded

    @staticmethod
    def _get_entity(project: Project, entity_id: object) -> object | None:
        for file in project.files:
            if file.id == entity_id:
                return file

        for directory in project.directories:
            if directory.id == entity_id:
                return directory

        for symbol in project.symbols:
            if symbol.id == entity_id:
                return symbol

        return None

    @staticmethod
    def _entity_type(entity: object) -> ContextUnitType:
        if entity.__class__.__name__ == "File":
            return ContextUnitType.FILE

        if entity.__class__.__name__ == "Directory":
            return ContextUnitType.DIRECTORY

        if entity.__class__.__name__ == "Symbol":
            return ContextUnitType.SYMBOL

        raise ValueError(f"Unsupported repository entity: {type(entity).__name__}")
