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
    RelationshipBuilder().build(project, project.imports)

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
    RelationshipBuilder().build(project, project.imports)

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


def test_symbol_schema_matches_symbol_model(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    with database.connect() as connection:
        columns = connection.execute("PRAGMA table_info(symbols)").fetchall()

    column_names = {column["name"] for column in columns}

    assert column_names == {
        "id",
        "file_id",
        "name",
        "kind",
        "qualified_name",
        "start_line",
        "end_line",
        "parent_symbol_id",
        "signature",
    }


def test_symbol_fields_survive_repository_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert len(loaded.symbols) == len(project.symbols)

    original = project.symbols
    restored = loaded.symbols

    for expected, actual in zip(original, restored):
        assert actual.id == expected.id
        assert actual.file_id == expected.file_id
        assert actual.name == expected.name
        assert actual.kind == expected.kind
        assert actual.qualified_name == expected.qualified_name
        assert actual.start_line == expected.start_line
        assert actual.end_line == expected.end_line
        assert actual.parent_symbol_id == expected.parent_symbol_id
        assert actual.signature == expected.signature


def test_project_save_removes_stale_symbols(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def first():
    return 1

def second():
    return 2
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    original_symbol_count = len(project.symbols)
    assert original_symbol_count == 2

    project.symbols = project.symbols[:1]
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert len(loaded.symbols) == 1
    assert loaded.symbols[0].name == "first"


def test_project_save_removes_stale_relationships(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
import os

def hello():
    return os.getcwd()
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    original_relationship_count = len(project.relationships)

    project.relationships = []
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert original_relationship_count > 0
    assert loaded.relationships == []
