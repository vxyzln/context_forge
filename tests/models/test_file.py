from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.enums import FileType
from context_forge.models.file import File


def test_file_creation() -> None:
    project_id = uuid4()

    file = File(
        project_id=project_id,
        path=Path("src/main.py"),
        name="main.py",
        extension=".py",
    )

    assert file.project_id == project_id
    assert file.path == Path("src/main.py")
    assert file.name == "main.py"
    assert file.extension == ".py"
    assert file.file_type == FileType.UNKNOWN
    assert file.size == 0
    assert file.is_generated is False
    assert file.is_ignored is False


def test_file_generates_unique_id() -> None:
    project_id = uuid4()

    file_a = File(
        project_id=project_id,
        path=Path("a.py"),
        name="a.py",
        extension=".py",
    )

    file_b = File(
        project_id=project_id,
        path=Path("b.py"),
        name="b.py",
        extension=".py",
    )

    assert file_a.id != file_b.id


def test_file_rejects_negative_size() -> None:
    with pytest.raises(ValueError, match="File size cannot be negative"):
        File(
            project_id=uuid4(),
            path=Path("bad.py"),
            name="bad.py",
            extension=".py",
            size=-1,
        )
