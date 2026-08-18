from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from context_forge.models.enums import DirectoryType


@dataclass
class Directory:
    project_id: UUID
    path: Path
    name: str
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None
    depth: int = 0
    directory_type: DirectoryType = DirectoryType.UNKNOWN

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("Directory depth cannot be negative")
