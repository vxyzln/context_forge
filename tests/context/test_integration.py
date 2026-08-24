from pathlib import Path

from context_forge.context import DefaultContextEngine, DeterministicRetriever
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


def test_context_engine_builds_package_from_project() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )

    file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(file)

    engine = DefaultContextEngine(
        retriever=DeterministicRetriever(),
    )

    package = engine.build(project, "auth")

    assert package.task == "auth"
    assert len(package.units) == 1
    assert package.units[0].entity_id == file.id
    assert package.units[0].relevance > 0
