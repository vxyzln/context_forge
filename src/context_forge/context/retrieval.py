from dataclasses import dataclass

from context_forge.context.candidate import ContextCandidate
from context_forge.context.types import ContextUnitType
from context_forge.models.project import Project
from context_forge.models.relationship import RelationshipType
from context_forge.query.project import ProjectQuery


@dataclass(frozen=True)
class RetrievalEvidence:
    source_candidate_id: object
    relationship_type: RelationshipType | str
    depth: int
    relationship_confidence: float
    candidate_confidence: float
    provenance: str

    def __post_init__(self) -> None:
        if self.depth < 1:
            raise ValueError("Retrieval evidence depth must be positive")

        if not 0.0 <= self.relationship_confidence <= 1.0:
            raise ValueError("Relationship confidence must be between 0.0 and 1.0")

        if not 0.0 <= self.candidate_confidence <= 1.0:
            raise ValueError("Candidate confidence must be between 0.0 and 1.0")

        if not self.provenance.strip():
            raise ValueError("Retrieval evidence provenance cannot be empty")


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
    ) -> tuple[list[ContextCandidate], dict[object, RetrievalEvidence]]:
        query = ProjectQuery(project)

        expanded = list(candidates)
        original_count = len(candidates)
        evidence: dict[object, RetrievalEvidence] = {}

        if self.max_candidates is not None and len(expanded) >= self.max_candidates:
            return self._sort_expanded(
                expanded[: self.max_candidates],
                evidence,
                original_count,
            )

        visited = {candidate.entity_id for candidate in candidates}
        frontier = list(candidates)

        for depth in range(1, self.max_depth + 1):
            next_frontier: list[ContextCandidate] = []

            for candidate in frontier:
                relationships = query.get_relationships(candidate.entity_id)

                for relationship in relationships:
                    relationship_type = relationship.relationship_type

                    if hasattr(relationship_type, "value"):
                        relationship_type = relationship_type.value

                    if (
                        self.relationship_types is not None
                        and relationship_type not in self.relationship_types
                    ):
                        continue

                    entity_id = (
                        relationship.target_id
                        if relationship.source_id == candidate.entity_id
                        else relationship.source_id
                    )

                    entity = self._get_entity(project, entity_id)

                    if entity is None:
                        continue

                    unit_type = self._entity_type(entity)

                    candidate_confidence = min(
                        candidate.score,
                        relationship.confidence,
                    )

                    new_evidence = RetrievalEvidence(
                        source_candidate_id=candidate.entity_id,
                        relationship_type=relationship_type,
                        depth=depth,
                        relationship_confidence=relationship.confidence,
                        candidate_confidence=candidate_confidence,
                        provenance="relationship-aware repository expansion",
                    )

                    existing_evidence = evidence.get(entity_id)

                    if existing_evidence is not None:
                        if self._evidence_is_stronger(
                            new_evidence,
                            existing_evidence,
                        ):
                            evidence[entity_id] = new_evidence

                        continue

                    if entity_id in visited:
                        continue

                    visited.add(entity_id)

                    expanded_candidate = ContextCandidate(
                        entity_id=entity_id,
                        unit_type=unit_type,
                        score=candidate_confidence,
                        source="relationship_expansion",
                        reason="Relationship-aware repository expansion",
                    )

                    evidence[entity_id] = new_evidence
                    expanded.append(expanded_candidate)
                    next_frontier.append(expanded_candidate)

                    if (
                        self.max_candidates is not None
                        and len(expanded) >= self.max_candidates
                    ):
                        return self._sort_expanded(
                            expanded,
                            evidence,
                            original_count,
                        )

            frontier = next_frontier

            if not frontier:
                break

        return self._sort_expanded(
            expanded,
            evidence,
            original_count,
        )

    @staticmethod
    def _evidence_is_stronger(
        candidate: RetrievalEvidence,
        existing: RetrievalEvidence,
    ) -> bool:
        candidate_key = (
            candidate.candidate_confidence,
            -candidate.depth,
            str(candidate.source_candidate_id),
        )
        existing_key = (
            existing.candidate_confidence,
            -existing.depth,
            str(existing.source_candidate_id),
        )
        return candidate_key > existing_key

    @staticmethod
    def _sort_expanded(
        candidates: list[ContextCandidate],
        evidence: dict[object, RetrievalEvidence],
        original_count: int,
    ) -> tuple[list[ContextCandidate], dict[object, RetrievalEvidence]]:
        originals = candidates[:original_count]

        additions = sorted(
            candidates[original_count:],
            key=lambda candidate: (
                -candidate.score,
                candidate.unit_type.value,
                str(candidate.entity_id),
            ),
        )

        ordered = originals + additions

        return ordered, {
            candidate.entity_id: evidence[candidate.entity_id]
            for candidate in ordered
            if candidate.entity_id in evidence
        }

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
