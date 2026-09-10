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
