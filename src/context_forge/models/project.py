from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from context_forge.git.models import GitActivitySummary
from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.parser.result import (
    ImportReference,
    InheritanceReference,
    SymbolReference,
)


@dataclass
class Project:
    name: str
    root_path: Path
    id: UUID = field(default_factory=uuid4)
    repository_url: str | None = None
    default_branch: str | None = None
    git_activity: GitActivitySummary | None = None
    project_type: str | None = None
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_manager: str | None = None
    analysis_status: str = "not_analyzed"
    directories: list[Directory] = field(default_factory=list)
    files: list[File] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportReference] = field(default_factory=list)
    references: list[SymbolReference] = field(default_factory=list)
    inheritance_references: list[InheritanceReference] = field(
        default_factory=list
    )
    relationships: list[Relationship] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Project name cannot be empty")

        if not self.root_path.is_absolute():
            raise ValueError("Project root path must be absolute")

    def add_directory(self, directory: Directory) -> None:
        if directory.project_id != self.id:
            raise ValueError("Directory belongs to a different project")

        self.directories.append(directory)

    def add_file(self, file: File) -> None:
        if file.project_id != self.id:
            raise ValueError("File belongs to a different project")

        self.files.append(file)

    def add_symbol(self, symbol: Symbol) -> None:
        if symbol.file_id not in {file.id for file in self.files}:
            raise ValueError("Symbol file does not belong to project")

        self.symbols.append(symbol)

    def add_reference(self, reference: SymbolReference) -> None:
        if reference.file_id not in {file.id for file in self.files}:
            raise ValueError("Reference file does not belong to project")

        self.references.append(reference)

    def add_inheritance_reference(
        self,
        reference: InheritanceReference,
    ) -> None:
        if reference.file_id not in {file.id for file in self.files}:
            raise ValueError(
                "Inheritance reference file does not belong to project"
            )

        if reference.class_symbol_id not in {
            symbol.id for symbol in self.symbols
        }:
            raise ValueError(
                "Inheritance reference class does not belong to project"
            )

        self.inheritance_references.append(reference)

    def add_relationship(self, relationship: Relationship) -> None:
        self.relationships.append(relationship)