from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol


@dataclass(frozen=True)
class ContainmentEdge:
    """Represent a structural parent-child relationship."""

    source_type: str
    source_id: UUID
    target_type: str
    target_id: UUID


@dataclass(frozen=True)
class UnresolvedImport:
    """Represent an import reference that could not be resolved against repository files."""

    file_id: UUID
    module_name: str
    imported_name: str | None = None
    alias: str | None = None
    level: int = 0
    source_path: Path | None = None

    @property
    def source_id(self) -> UUID:
        return self.file_id


@dataclass(frozen=True)
class StructuralIntegrityFinding:
    """Represent an issue with repository structural references."""

    finding_type: str
    message: str
    source_type: str | None = None
    source_id: UUID | None = None
    source_path: str | None = None
    target_type: str | None = None
    target_id: UUID | None = None

    @property
    def kind(self) -> str:
        return self.finding_type

    @property
    def description(self) -> str:
        return self.message


StructuralFinding = StructuralIntegrityFinding


@dataclass(frozen=True)
class ArchitectureInventory:
    """Provide a deterministic view of the analyzed repository structure."""

    project_id: UUID
    analysis_status: str
    errors: tuple[str, ...]
    directories: tuple[Directory, ...]
    files: tuple[File, ...]
    symbols: tuple[Symbol, ...]
    containment: tuple[ContainmentEdge, ...]
    dependencies: tuple[Relationship, ...]
    unresolved_imports: tuple[UnresolvedImport, ...] = ()
    integrity_findings: tuple[StructuralIntegrityFinding, ...] = ()

    @property
    def structural_findings(self) -> tuple[StructuralIntegrityFinding, ...]:
        return self.integrity_findings
