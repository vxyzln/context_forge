from pathlib import Path

import pytest

from context_forge.context import (
    DefaultContextEngine,
    DeterministicRetriever,
)
from context_forge.context.candidate import ContextCandidate
from context_forge.context.types import ContextUnitType
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
    assert package.units[0].unit_type == ContextUnitType.FILE
    assert package.units[0].relevance > 0


def test_default_context_engine_rejects_empty_task() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    engine = DefaultContextEngine(DeterministicRetriever())

    with pytest.raises(ValueError, match="Task cannot be empty"):
        engine.build(project, "   ")


def test_default_context_engine_ranks_candidates() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)

    class TestCandidateGenerator:
        def generate(self, project: Project, task: str):
            return [
                ContextCandidate(
                    entity_id=first.id,
                    unit_type=ContextUnitType.FILE,
                    score=0.3,
                    source="test",
                ),
                ContextCandidate(
                    entity_id=second.id,
                    unit_type=ContextUnitType.FILE,
                    score=0.8,
                    source="test",
                ),
            ]

    engine = DefaultContextEngine(
        retriever=DeterministicRetriever(),
        candidate_generator=TestCandidateGenerator(),
    )

    package = engine.build(project, "anything")

    assert package.units[0].entity_id == second.id
    assert package.units[0].relevance == 0.8
    assert package.units[1].entity_id == first.id
