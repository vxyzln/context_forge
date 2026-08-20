from dataclasses import dataclass, field
from uuid import UUID

from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol


@dataclass(frozen=True)
class ParseError:
    message: str
    file_id: UUID
    line: int | None = None
    column: int | None = None


@dataclass
class ParseResult:
    symbols: list[Symbol] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors
