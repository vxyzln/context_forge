from pathlib import Path

import pytest

from context_forge.context import BasicContextEngine
from context_forge.models.project import Project


def test_basic_context_engine_builds_package() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    package = BasicContextEngine().build(
        project,
        "Fix authentication",
    )

    assert package.task == "Fix authentication"
    assert package.units == ()


def test_basic_context_engine_rejects_empty_task() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    with pytest.raises(ValueError, match="Task cannot be empty"):
        BasicContextEngine().build(project, "   ")
