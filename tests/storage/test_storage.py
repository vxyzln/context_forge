from pathlib import Path
from uuid import uuid4

from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
from context_forge.parser.python import PythonParser
from context_forge.scanner.repository import RepositoryScanner
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def parse_project(project: Project) -> None:
    parser = PythonParser()

    for file in project.files:
        if file.extension != ".py":
            continue

        source = (project.root_path / file.path).read_text(encoding="utf-8")
        result = parser.parse(source, file)

        for symbol in result.symbols:
            project.add_symbol(symbol)


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


def test_analyzed_project_persists_analysis_records(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    with database.connect() as connection:
        project_row = connection.execute(
            "SELECT COUNT(*) AS count FROM projects WHERE id = ?",
            (str(project.id),),
        ).fetchone()

        directory_row = connection.execute(
            "SELECT COUNT(*) AS count FROM directories WHERE project_id = ?",
            (str(project.id),),
        ).fetchone()

        file_row = connection.execute(
            "SELECT COUNT(*) AS count FROM files WHERE project_id = ?",
            (str(project.id),),
        ).fetchone()

        symbol_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM symbols
            WHERE file_id IN (
                SELECT id FROM files WHERE project_id = ?
            )
            """,
            (str(project.id),),
        ).fetchone()

        relationship_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM relationships
            WHERE source_id IN (
                SELECT id FROM files WHERE project_id = ?
            )
            """,
            (str(project.id),),
        ).fetchone()

    assert project_row["count"] == 1
    assert directory_row["count"] == len(project.directories)
    assert file_row["count"] == len(project.files)
    assert symbol_row["count"] == len(project.symbols)
    assert relationship_row["count"] == len(project.relationships)


def test_analysis_errors_are_persisted(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
        errors=["main.py:1:1: Invalid syntax"],
    )

    repository.save(project)

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT message
            FROM analysis_errors
            WHERE project_id = ?
            """,
            (str(project.id),),
        ).fetchone()

    assert row is not None
    assert row["message"] == "main.py:1:1: Invalid syntax"


def test_project_load_rehydrates_analysis_records(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project)

    project.errors.append("example.py:1:1: Invalid syntax")

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None

    assert loaded.id == project.id
    assert loaded.name == project.name
    assert loaded.root_path == project.root_path

    assert len(loaded.directories) == len(project.directories)
    assert len(loaded.files) == len(project.files)
    assert len(loaded.symbols) == len(project.symbols)
    assert len(loaded.relationships) == len(project.relationships)
    assert loaded.errors == project.errors

    assert loaded.files[0].id == project.files[0].id
    assert loaded.files[0].path == project.files[0].path

    assert loaded.symbols[0].id == project.symbols[0].id
    assert loaded.symbols[0].name == project.symbols[0].name

    assert loaded.relationships[0].id == project.relationships[0].id
    assert (
        loaded.relationships[0].relationship_type
        == project.relationships[0].relationship_type
    )
