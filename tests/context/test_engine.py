from pathlib import Path

import pytest

from context_forge.context import (
    DefaultContextEngine,
    DeterministicRetriever,
)
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


def test_default_context_engine_builds_context_from_retriever() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    file = File(
        project_id=project.id,
        path=Path("src/auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(file)

    engine = DefaultContextEngine(DeterministicRetriever())

    package = engine.build(project, "auth")

    assert package.task == "auth"
    assert len(package.units) == 1
    assert package.units[0].entity_id == file.id
    assert package.units[0].unit_type == "file"
    assert package.units[0].relevance > 0


def test_default_context_engine_rejects_empty_task() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    engine = DefaultContextEngine(DeterministicRetriever())

    with pytest.raises(ValueError, match="Task cannot be empty"):
        engine.build(project, "   ")
