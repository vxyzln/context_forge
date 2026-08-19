from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Symbol:
    file_id: UUID
    name: str
    kind: str
    start_line: int
    end_line: int
    id: UUID = field(default_factory=uuid4)
    qualified_name: str | None = None
    parent_symbol_id: UUID | None = None
    signature: str | None = None
