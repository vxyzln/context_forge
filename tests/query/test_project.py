from pathlib import Path
from uuid import uuid4

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.query import ProjectQuery
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def create_project(tmp_path: Path) -> Project:
    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    main_file = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )

    utils_file = File(
        project_id=project.id,
        path=Path("utils.py"),
        name="utils.py",
        extension=".py",
    )

    project.add_file(main_file)
    project.add_file(utils_file)

    calculator = Symbol(
        file_id=main_file.id,
        name="Calculator",
        kind="class",
        start_line=1,
        end_line=5,
        qualified_name="Calculator",
    )

    hello = Symbol(
        file_id=main_file.id,
        name="hello",
        kind="function",
        start_line=7,
        end_line=8,
        qualified_name="hello",
    )

    utility = Symbol(
        file_id=utils_file.id,
        name="hello",
        kind="function",
        start_line=1,
        end_line=2,
        qualified_name="hello",
    )

    project.add_symbol(calculator)
    project.add_symbol(hello)
    project.add_symbol(utility)

    project.add_relationship(
        Relationship(
            source_id=main_file.id,
            target_id=utils_file.id,
            relationship_type="imports",
        )
    )

    return project


def test_query_finds_file_by_path(tmp_path: Path) -> None:
    project = create_project(tmp_path)
    query = ProjectQuery(project)

    file = query.get_file("main.py")

    assert file is not None
    assert file.name == "main.py"


def test_query_returns_none_for_unknown_file(tmp_path: Path) -> None:
    project = create_project(tmp_path)
    query = ProjectQuery(project)

    assert query.get_file("missing.py") is None


def test_query_finds_symbols_by_name(tmp_path: Path) -> None:
    project = create_project(tmp_path)
    query = ProjectQuery(project)

    symbols = query.find_symbols("hello")

    assert len(symbols) == 2
    assert {symbol.file_id for symbol in symbols} == {
        project.files[0].id,
        project.files[1].id,
    }


def test_query_finds_symbols_in_file(tmp_path: Path) -> None:
    project = create_project(tmp_path)
    query = ProjectQuery(project)

    symbols = query.find_symbols_in_file(project.files[0].id)

    assert len(symbols) == 2
    assert {symbol.name for symbol in symbols} == {
        "Calculator",
        "hello",
    }


def test_query_finds_relationships_for_entity(tmp_path: Path) -> None:
    project = create_project(tmp_path)
    query = ProjectQuery(project)

    relationship = project.relationships[0]

    source_relationships = query.get_relationships(relationship.source_id)
    target_relationships = query.get_relationships(relationship.target_id)

    assert len(source_relationships) == 1
    assert len(target_relationships) == 1
    assert source_relationships[0].id == relationship.id
    assert target_relationships[0].id == relationship.id


def test_query_returns_empty_relationships_for_unknown_entity(
    tmp_path: Path,
) -> None:
    project = create_project(tmp_path)
    query = ProjectQuery(project)

    assert query.get_relationships(uuid4()) == []


def test_query_can_load_project_from_repository(tmp_path: Path) -> None:
    project = create_project(tmp_path)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    query = ProjectQuery.from_repository(repository, project.id)

    assert query is not None
    assert query.get_file("main.py") is not None
    assert len(query.find_symbols("hello")) == 2


def test_query_returns_none_for_missing_project(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    query = ProjectQuery.from_repository(repository, uuid4())

    assert query is None
