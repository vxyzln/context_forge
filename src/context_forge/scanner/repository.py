import os
from pathlib import Path

from context_forge.models.directory import Directory
from context_forge.models.enums import DirectoryType, FileType
from context_forge.models.file import File
from context_forge.models.project import Project

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
}

IGNORED_FILES = {
    ".context_forge.db",
}

GENERATED_DIRECTORIES = {
    "__pycache__",
    "build",
    "dist",
    ".eggs",
}

TEST_DIRECTORIES = {
    "test",
    "tests",
}

DOCUMENTATION_DIRECTORIES = {
    "docs",
    "doc",
    "documentation",
}

CONFIGURATION_DIRECTORIES = {
    "config",
    "configs",
}

ASSET_DIRECTORIES = {
    "assets",
    "static",
    "resources",
}

DEPENDENCY_DIRECTORIES = {
    "site-packages",
    "node_modules",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".pyi",
}

TEST_FILE_PREFIXES = ("test_",)

TEST_FILE_SUFFIXES = ("_test.py",)

DOCUMENTATION_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
}

CONFIGURATION_EXTENSIONS = {
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".json",
}

DATA_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".xml",
}

ASSET_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
}


class RepositoryScanner:
    def __init__(
        self,
        root_path: Path,
        ignored_files: set[Path] | None = None,
    ) -> None:
        self.root_path = root_path.resolve()

        if not self.root_path.exists():
            raise ValueError("Repository path does not exist")

        if not self.root_path.is_dir():
            raise ValueError("Repository path must be a directory")

        self.ignored_files: set[Path] = set()
        if ignored_files:
            for f in ignored_files:
                self.ignored_files.add(f)
                try:
                    self.ignored_files.add(f.resolve())
                except OSError:
                    pass

    def scan(self) -> Project:
        project = Project(
            name=self.root_path.name,
            root_path=self.root_path,
        )

        self._scan_directories(project)
        self._scan_files(project)

        return project

    def _iter_directories(self) -> list[Path]:
        directories = []
        for root, dirnames, _ in os.walk(self.root_path):
            dirnames[:] = [
                d
                for d in dirnames
                if not self._is_ignored_path(Path(root) / d)
                and not (Path(root) / d).is_symlink()
            ]
            dirnames.sort()
            for d in dirnames:
                directories.append(Path(root) / d)
        return directories

    def _is_ignored_file(self, path: Path) -> bool:
        if path.name in IGNORED_FILES:
            return True
        if self.ignored_files:
            if path in self.ignored_files:
                return True
            try:
                if path.resolve() in self.ignored_files:
                    return True
            except OSError:
                pass
        return False

    def _iter_files(self) -> list[Path]:
        files = []
        for root, dirnames, filenames in os.walk(self.root_path):
            dirnames[:] = [
                d
                for d in dirnames
                if not self._is_ignored_path(Path(root) / d)
                and not (Path(root) / d).is_symlink()
            ]
            dirnames.sort()
            filenames.sort()
            for f in filenames:
                p = Path(root) / f
                if (
                    p.is_file()
                    and not p.is_symlink()
                    and not self._is_ignored_file(p)
                    and not self._is_ignored_path(p)
                ):
                    files.append(p)
        return files

    def _is_ignored_path(self, path: Path) -> bool:
        return any(
            part in IGNORED_DIRECTORIES
            for part in path.relative_to(self.root_path).parts
        )

    def _scan_directories(self, project: Project) -> None:
        directory_map: dict[Path, Directory] = {
            self.root_path: Directory(
                project_id=project.id,
                path=Path("."),
                name=self.root_path.name,
                depth=0,
                directory_type=DirectoryType.SOURCE,
            )
        }

        project.add_directory(directory_map[self.root_path])

        for directory_path in sorted(
            self._iter_directories(),
            key=lambda path: path.relative_to(self.root_path).as_posix(),
        ):
            relative_path = directory_path.relative_to(self.root_path)
            parent_path = directory_path.parent
            parent = directory_map.get(parent_path)
            if parent is None:
                project.errors.append(
                    f"Inconsistent directory structure: parent directory '{parent_path}' not found for '{relative_path}'"
                )
                continue

            directory = Directory(
                project_id=project.id,
                path=relative_path,
                name=directory_path.name,
                parent_id=parent.id,
                depth=len(relative_path.parts),
                directory_type=self._classify_directory(directory_path),
            )

            directory_map[directory_path] = directory
            project.add_directory(directory)

    def _scan_files(self, project: Project) -> None:
        directory_lookup = {
            directory.path: directory for directory in project.directories
        }

        for file_path in sorted(
            self._iter_files(),
            key=lambda path: path.relative_to(self.root_path).as_posix(),
        ):
            relative_path = file_path.relative_to(self.root_path)
            directory_path = (
                Path(".") if relative_path.parent == Path(".") else relative_path.parent
            )

            directory = directory_lookup.get(directory_path)
            if directory is None:
                project.errors.append(
                    f"Inconsistent directory structure: directory '{directory_path}' not found for file '{relative_path}'"
                )
                continue

            try:
                file_size = file_path.stat().st_size
            except FileNotFoundError:
                continue

            is_generated = self._is_generated(relative_path)
            is_ignored = file_path.name in IGNORED_FILES

            file = File(
                project_id=project.id,
                directory_id=directory.id,
                path=relative_path,
                name=file_path.name,
                extension=file_path.suffix.lower(),
                file_type=self._classify_file(relative_path, is_generated),
                size=file_size,
                is_generated=is_generated,
                is_ignored=is_ignored,
            )

            project.add_file(file)

    def _classify_directory(self, path: Path) -> DirectoryType:
        name = path.name.lower()

        if name in GENERATED_DIRECTORIES:
            return DirectoryType.GENERATED

        if name in DEPENDENCY_DIRECTORIES:
            return DirectoryType.DEPENDENCY

        if name in TEST_DIRECTORIES:
            return DirectoryType.TESTS

        if name in DOCUMENTATION_DIRECTORIES:
            return DirectoryType.DOCUMENTATION

        if name in CONFIGURATION_DIRECTORIES:
            return DirectoryType.CONFIGURATION

        if name in ASSET_DIRECTORIES:
            return DirectoryType.ASSETS

        if name in {"src", "lib", "app", "python"}:
            return DirectoryType.SOURCE

        return DirectoryType.UNKNOWN

    def _is_generated(self, path: Path) -> bool:
        return any(part in GENERATED_DIRECTORIES for part in path.parts)

    def _classify_file(self, path: Path, is_generated: bool) -> FileType:
        if is_generated:
            return FileType.GENERATED

        name = path.name.lower()
        extension = path.suffix.lower()

        if any(name.startswith(prefix) for prefix in TEST_FILE_PREFIXES) or any(
            name.endswith(suffix) for suffix in TEST_FILE_SUFFIXES
        ):
            return FileType.TEST

        if extension in DOCUMENTATION_EXTENSIONS or name in {
            "readme",
            "license",
            "licence",
            "changelog",
        }:
            return FileType.DOCUMENTATION

        if extension in CONFIGURATION_EXTENSIONS or name in {
            ".gitignore",
            ".dockerignore",
        }:
            return FileType.CONFIGURATION

        if extension in DATA_EXTENSIONS:
            return FileType.DATA

        if extension in ASSET_EXTENSIONS:
            return FileType.ASSET

        if extension in SOURCE_EXTENSIONS:
            return FileType.SOURCE

        if any(part in DEPENDENCY_DIRECTORIES for part in path.parts):
            return FileType.DEPENDENCY

        return FileType.UNKNOWN
