from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project


def test_project_creation() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    assert project.name == "Context Forge"
    assert project.root_path == Path.cwd()
    assert project.languages == []
    assert project.frameworks == []
    assert project.directories == []
    assert project.files == []
    assert project.analysis_status == "not_analyzed"


def test_project_adds_directory() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    directory = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
    )

    project.add_directory(directory)

    assert project.directories == [directory]


def test_project_adds_file() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file = File(
        project_id=project.id,
        path=Path("README.md"),
        name="README.md",
        extension=".md",
    )

    project.add_file(file)

    assert project.files == [file]


def test_project_rejects_foreign_directory() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    directory = Directory(
        project_id=uuid4(),
        path=Path("src"),
        name="src",
    )

    with pytest.raises(ValueError, match="Directory belongs to a different project"):
        project.add_directory(directory)


def test_project_rejects_foreign_file() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file = File(
        project_id=uuid4(),
        path=Path("README.md"),
        name="README.md",
        extension=".md",
    )

    with pytest.raises(ValueError, match="File belongs to a different project"):
        project.add_file(file)


def test_project_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="Project name cannot be empty"):
        Project(
            name="   ",
            root_path=Path.cwd(),
        )


def test_project_rejects_relative_root() -> None:
    with pytest.raises(ValueError, match="Project root path must be absolute"):
        Project(
            name="Context Forge",
            root_path=Path("context_forge"),
        )
