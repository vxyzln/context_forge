from pathlib import Path

from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
from context_forge.parser.python import PythonParser
from context_forge.scanner.repository import RepositoryScanner


def parse_project(project: Project) -> None:
    parser = PythonParser()

    for file in project.files:
        if file.extension != ".py":
            continue

        source = (project.root_path / file.path).read_text(encoding="utf-8")
        result = parser.parse(source, file)

        for symbol in result.symbols:
            project.add_symbol(symbol)

        for import_reference in result.imports:
            project.imports.append(import_reference)


def test_builder_creates_definition_relationships(tmp_path: Path) -> None:
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

    definitions = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "defines"
    ]

    assert len(definitions) == 1
    assert definitions[0].source_id == project.files[0].id
    assert definitions[0].target_id == project.symbols[0].id


def test_builder_creates_import_relationship(tmp_path: Path) -> None:
    package = tmp_path / "app"
    package.mkdir()

    (package / "utils.py").write_text(
        """
def hello():
    return "hello"
"""
    )

    (package / "main.py").write_text(
        """
from app.utils import hello
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project)

    imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    assert len(imports) == 1


def test_builder_does_not_duplicate_relationships(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    builder = RelationshipBuilder()

    builder.build(project)
    first_count = len(project.relationships)

    builder.build(project)
    second_count = len(project.relationships)

    assert first_count > 0
    assert second_count == first_count


def test_builder_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    builder = RelationshipBuilder()

    builder.build(project)

    first_relationships = [
        (
            relationship.source_id,
            relationship.target_id,
            relationship.relationship_type,
        )
        for relationship in project.relationships
    ]

    builder.build(project)

    second_relationships = [
        (
            relationship.source_id,
            relationship.target_id,
            relationship.relationship_type,
        )
        for relationship in project.relationships
    ]

    assert first_relationships == second_relationships


def test_builder_does_not_duplicate_import_relationships(tmp_path: Path) -> None:
    package = tmp_path / "app"
    package.mkdir()

    (package / "__init__.py").write_text("")
    (package / "utils.py").write_text(
        """
def hello():
    return "hello"
"""
    )
    (package / "main.py").write_text(
        """
from app.utils import hello
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    builder = RelationshipBuilder()

    builder.build(project)

    first_imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    builder.build(project)

    second_imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    assert len(first_imports) == len(second_imports)
    assert len(second_imports) == 1
