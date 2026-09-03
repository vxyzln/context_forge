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

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Symbol name cannot be empty")

        if not self.kind.strip():
            raise ValueError("Symbol kind cannot be empty")

        if self.start_line < 1:
            raise ValueError("Symbol start line must be positive")

        if self.end_line < self.start_line:
            raise ValueError("Symbol end line cannot precede start line")

        if self.qualified_name is not None and not self.qualified_name.strip():
            raise ValueError("Symbol qualified name cannot be empty")

        if self.signature is not None and not self.signature.strip():
            raise ValueError("Symbol signature cannot be empty")