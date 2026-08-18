from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from context_forge.models.enums import FileType


@dataclass
class File:
    project_id: UUID
    path: Path
    name: str
    extension: str

    id: UUID = field(default_factory=uuid4)
    directory_id: UUID | None = None
    file_type: FileType = FileType.UNKNOWN
    size: int = 0
    is_generated: bool = False
    is_ignored: bool = False

    def __post_init__(self) -> None:
        if self.size < 0:
            raise ValueError("File size cannot be negative")
