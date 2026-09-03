from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4


class RelationshipType(str, Enum):
    DEFINES = "defines"
    IMPORTS = "imports"
    REFERENCES = "references"
    CALLS = "calls"
    INHERITS = "inherits"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"


@dataclass
class Relationship:
    source_id: UUID
    target_id: UUID
    relationship_type: RelationshipType | str
    id: UUID = field(default_factory=uuid4)
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Relationship confidence must be between 0.0 and 1.0")

        if not str(self.relationship_type):
            raise ValueError("Relationship type cannot be empty")
