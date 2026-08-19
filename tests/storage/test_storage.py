from pathlib import Path
from uuid import uuid4

from context_forge.models.project import Project
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def test_database_initializes(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")

    database.initialize()

    assert database.path.exists()


def test_project_can_be_saved_and_loaded(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert loaded.id == project.id
    assert loaded.name == "Test Project"
    assert loaded.root_path == tmp_path


def test_missing_project_returns_none(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    loaded = repository.load(uuid4())

    assert loaded is None
