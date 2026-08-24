from pathlib import Path

from context_forge.context import DeterministicRetriever
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


def test_deterministic_retriever_uses_project_query() -> None:
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

    results = DeterministicRetriever().retrieve(project, "auth")

    assert len(results) == 1
    assert results[0].entity_id == file.id
    assert results[0].unit_type == "file"
    assert results[0].relevance > 0
