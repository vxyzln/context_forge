from dataclasses import dataclass
from pathlib import Path

from context_forge.models.relationship import RelationshipType


@dataclass(frozen=True)
class ExpectedFile:
    path: Path


@dataclass(frozen=True)
class ExpectedSymbol:
    qualified_name: str
    file_path: Path


@dataclass(frozen=True)
class ExpectedRelationship:
    source: str
    target: str
    relationship_type: RelationshipType | str


@dataclass(frozen=True)
class StructuralGroundTruth:
    files: tuple[ExpectedFile, ...] = ()
    symbols: tuple[ExpectedSymbol, ...] = ()
    relationships: tuple[ExpectedRelationship, ...] = ()


@dataclass(frozen=True)
class ExpectedEntity:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("Expected entity kind must not be empty")
        if not self.value.strip():
            raise ValueError("Expected entity value must not be empty")


@dataclass(frozen=True)
class RetrievalGroundTruth:
    retrieved_entities: tuple[ExpectedEntity, ...] = ()
    grounded_entities: tuple[ExpectedEntity, ...] = ()
