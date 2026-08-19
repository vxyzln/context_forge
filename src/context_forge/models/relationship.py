from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Relationship:
    source_id: UUID
    target_id: UUID
    relationship_type: str
    id: UUID = field(default_factory=uuid4)
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Relationship confidence must be between 0.0 and 1.0")
