from dataclasses import dataclass, field
from uuid import UUID

from context_forge.models.relationship import RelationshipType


@dataclass(frozen=True)
class TaskInterpretation:
    task: str
    intent: str
    target: str | None
    concepts: tuple[str, ...] = field(default_factory=tuple)
    requested_action: str | None = None
    constraints: tuple[str, ...] = field(default_factory=tuple)
    ambiguity: str | None = None


@dataclass(frozen=True)
class TaskReference:
    value: str
    kind: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("Task reference value cannot be empty")

        if not self.kind.strip():
            raise ValueError("Task reference kind cannot be empty")


@dataclass(frozen=True)
class GroundedEntity:
    entity_id: UUID
    entity_type: str
    reference: str
    confidence: float
    provenance: str

    def __post_init__(self) -> None:
        if not self.entity_type.strip():
            raise ValueError("Grounded entity type cannot be empty")

        if not self.reference.strip():
            raise ValueError("Grounded entity reference cannot be empty")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Grounded entity confidence must be between 0.0 and 1.0")

        if not self.provenance.strip():
            raise ValueError("Grounded entity provenance cannot be empty")


@dataclass(frozen=True)
class GroundedTask:
    interpretation: TaskInterpretation
    entities: tuple[GroundedEntity, ...] = field(default_factory=tuple)
    unresolved_references: tuple[TaskReference, ...] = field(default_factory=tuple)
    ambiguous_references: tuple[TaskReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GroundedRelationship:
    source_id: UUID
    target_id: UUID
    relationship_type: RelationshipType | str
    depth: int
    confidence: float
    provenance: str

    def __post_init__(self) -> None:
        if self.depth < 1:
            raise ValueError("Grounded relationship depth must be positive")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Grounded relationship confidence must be between 0.0 and 1.0"
            )

        if not self.provenance.strip():
            raise ValueError("Grounded relationship provenance cannot be empty")


@dataclass(frozen=True)
class RepositoryGrounding:
    task: GroundedTask
    related_entity_ids: tuple[UUID, ...] = field(default_factory=tuple)
    relationships: tuple[GroundedRelationship, ...] = field(default_factory=tuple)
    max_depth: int = 1

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("Repository grounding depth cannot be negative")
