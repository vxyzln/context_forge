from uuid import UUID

from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.query.project import ProjectQuery

from .models import GroundedRelationship, GroundedTask, RepositoryGrounding


class TaskRepositoryGroundingService:
    """Expand task-grounded entities through repository relationships."""

    def __init__(self, max_depth: int = 1) -> None:
        if max_depth < 0:
            raise ValueError("Repository grounding depth cannot be negative")

        self.max_depth = max_depth

    def ground(
        self,
        project: Project,
        task: GroundedTask,
        max_depth: int | None = None,
    ) -> RepositoryGrounding:
        depth = self.max_depth if max_depth is None else max_depth

        if depth < 0:
            raise ValueError("Repository grounding depth cannot be negative")

        if depth == 0 or not task.entities:
            return RepositoryGrounding(
                task=task,
                max_depth=depth,
            )

        query = ProjectQuery(project)

        direct_entity_ids = {entity.entity_id for entity in task.entities}

        visited = set(direct_entity_ids)
        frontier = sorted(direct_entity_ids, key=str)

        related_entity_ids: list[UUID] = []
        relationships: list[GroundedRelationship] = []

        for current_depth in range(1, depth + 1):
            next_frontier: list[UUID] = []

            for entity_id in frontier:
                for relationship in query.get_relationships(entity_id):
                    related_id = self._other_entity_id(
                        relationship,
                        entity_id,
                    )

                    if related_id is None or related_id in visited:
                        continue

                    visited.add(related_id)
                    next_frontier.append(related_id)
                    related_entity_ids.append(related_id)

                    relationships.append(
                        GroundedRelationship(
                            source_id=relationship.source_id,
                            target_id=relationship.target_id,
                            relationship_type=relationship.relationship_type,
                            depth=current_depth,
                            confidence=relationship.confidence,
                            provenance="repository relationship traversal",
                        )
                    )

            if not next_frontier:
                break

            frontier = sorted(next_frontier, key=str)

        return RepositoryGrounding(
            task=task,
            related_entity_ids=tuple(related_entity_ids),
            relationships=tuple(relationships),
            max_depth=depth,
        )

    @staticmethod
    def _other_entity_id(
        relationship: Relationship,
        entity_id: UUID,
    ) -> UUID | None:
        if relationship.source_id == entity_id:
            return relationship.target_id

        if relationship.target_id == entity_id:
            return relationship.source_id

        return None
