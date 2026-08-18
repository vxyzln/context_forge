from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.directory import Directory
from context_forge.models.enums import DirectoryType


def test_directory_creation() -> None:
    project_id = uuid4()

    directory = Directory(
        project_id=project_id,
        path=Path("src"),
        name="src",
    )

    assert directory.project_id == project_id
    assert directory.path == Path("src")
    assert directory.name == "src"
    assert directory.parent_id is None
    assert directory.depth == 0
    assert directory.directory_type == DirectoryType.UNKNOWN


def test_directory_supports_parent() -> None:
    project_id = uuid4()

    parent = Directory(
        project_id=project_id,
        path=Path("src"),
        name="src",
    )

    child = Directory(
        project_id=project_id,
        path=Path("src/models"),
        name="models",
        parent_id=parent.id,
        depth=1,
    )

    assert child.parent_id == parent.id
    assert child.depth == 1


def test_directory_rejects_negative_depth() -> None:
    with pytest.raises(ValueError, match="Directory depth cannot be negative"):
        Directory(
            project_id=uuid4(),
            path=Path("bad"),
            name="bad",
            depth=-1,
        )
