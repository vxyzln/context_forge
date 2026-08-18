from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from context_forge.models.directory import Directory
from context_forge.models.file import File


@dataclass
class Project:
    name: str
    root_path: Path

    id: UUID = field(default_factory=uuid4)
    repository_url: str | None = None
    default_branch: str | None = None
    project_type: str | None = None

    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_manager: str | None = None

    analysis_status: str = "not_analyzed"

    directories: list[Directory] = field(default_factory=list)
    files: list[File] = field(default_factory=list)

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

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
