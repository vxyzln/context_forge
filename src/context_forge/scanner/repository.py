from pathlib import Path

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}

GENERATED_DIRECTORIES = {
    "__pycache__",
    "build",
    "dist",
}


class RepositoryScanner:
    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path.resolve()

        if not self.root_path.exists():
            raise ValueError("Repository path does not exist")

        if not self.root_path.is_dir():
            raise ValueError("Repository path must be a directory")

    def scan(self) -> Project:
        project = Project(
            name=self.root_path.name,
            root_path=self.root_path,
        )

        self._scan_directories(project)
        self._scan_files(project)

        return project

    def _iter_directories(self) -> list[Path]:
        return [
            path
            for path in self.root_path.rglob("*")
            if path.is_dir()
            and not any(part in IGNORED_DIRECTORIES for part in path.parts)
        ]

    def _iter_files(self) -> list[Path]:
        return [
            path
            for path in self.root_path.rglob("*")
            if path.is_file()
            and not any(part in IGNORED_DIRECTORIES for part in path.parts)
        ]

    def _scan_directories(self, project: Project) -> None:
        directory_map: dict[Path, Directory] = {
            self.root_path: Directory(
                project_id=project.id,
                path=Path("."),
                name=self.root_path.name,
                depth=0,
            )
        }

        project.add_directory(directory_map[self.root_path])

        for directory_path in sorted(self._iter_directories()):
            relative_path = directory_path.relative_to(self.root_path)
            parent_path = directory_path.parent

            parent = directory_map[parent_path]

            directory = Directory(
                project_id=project.id,
                path=relative_path,
                name=directory_path.name,
                parent_id=parent.id,
                depth=len(relative_path.parts),
            )

            directory_map[directory_path] = directory
            project.add_directory(directory)

    def _scan_files(self, project: Project) -> None:
        directory_lookup = {
            directory.path: directory for directory in project.directories
        }

        for file_path in sorted(self._iter_files()):
            relative_path = file_path.relative_to(self.root_path)
            directory_path = (
                Path(".") if relative_path.parent == Path(".") else relative_path.parent
            )

            directory = directory_lookup[directory_path]

            file = File(
                project_id=project.id,
                directory_id=directory.id,
                path=relative_path,
                name=file_path.name,
                extension=file_path.suffix,
                size=file_path.stat().st_size,
                is_generated=any(
                    part in GENERATED_DIRECTORIES for part in relative_path.parts
                ),
            )

            project.add_file(file)


if __name__ == "__main__":
    scanner = RepositoryScanner(Path.cwd())
    project = scanner.scan()
    print(project.name)
