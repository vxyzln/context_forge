from pathlib import Path

from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
from context_forge.models.relationship import RelationshipType
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

        project.imports.extend(result.imports)
        project.references.extend(result.references)
        project.inheritance_references.extend(result.inheritance_references)


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
    RelationshipBuilder().build(project, project.imports)

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
    RelationshipBuilder().build(project, project.imports)

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

    builder.build(project, project.imports)
    first_count = len(project.relationships)

    builder.build(project, project.imports)
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

    builder.build(project, project.imports)

    first_relationships = [
        (
            relationship.source_id,
            relationship.target_id,
            relationship.relationship_type,
        )
        for relationship in project.relationships
    ]

    builder.build(project, project.imports)

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

    builder.build(project, project.imports)

    first_imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    builder.build(project, project.imports)

    second_imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    assert len(first_imports) == len(second_imports)
    assert len(second_imports) == 1


def test_builder_explicit_import_references(tmp_path: Path) -> None:
    from context_forge.parser.result import ImportReference

    package = tmp_path / "app"
    package.mkdir()

    (package / "utils.py").write_text(
        """
def hello():
    return "hello"
"""
    )

    source_file = package / "main.py"
    source_file.write_text(
        """
from app.utils import hello
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    main_file_id = next(f.id for f in project.files if f.name == "main.py")
    utils_file_id = next(f.id for f in project.files if f.name == "utils.py")

    explicit_references = [
        ImportReference(file_id=main_file_id, module_name="app.utils")
    ]

    project.imports.clear()

    builder = RelationshipBuilder()
    builder.build(project, explicit_references)

    imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    assert len(imports) == 1
    assert imports[0].source_id == main_file_id
    assert imports[0].target_id == utils_file_id


def test_builds_same_file_reference_relationship(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def helper() -> None:
    pass


def main() -> None:
    helper()
""",
        encoding="utf-8",
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    helper = next(symbol for symbol in project.symbols if symbol.name == "helper")

    relationships = [
        relationship
        for relationship in project.relationships
        if relationship.target_id == helper.id
        and relationship.relationship_type == RelationshipType.REFERENCES
    ]

    assert len(relationships) == 1
    assert relationships[0].confidence == 0.8


def test_builds_imported_reference_relationship(
    tmp_path: Path,
) -> None:
    (tmp_path / "base.py").write_text(
        """
class Base:
    pass
""",
        encoding="utf-8",
    )

    (tmp_path / "child.py").write_text(
        """
from base import Base


def use() -> None:
    Base()
""",
        encoding="utf-8",
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    base = next(symbol for symbol in project.symbols if symbol.name == "Base")

    relationships = [
        relationship
        for relationship in project.relationships
        if relationship.target_id == base.id
        and relationship.relationship_type == RelationshipType.REFERENCES
    ]

    assert len(relationships) == 1
    assert relationships[0].confidence == 0.9


def test_builds_inheritance_relationship(
    tmp_path: Path,
) -> None:
    (tmp_path / "base.py").write_text(
        """
class Base:
    pass
""",
        encoding="utf-8",
    )

    (tmp_path / "child.py").write_text(
        """
from base import Base


class Child(Base):
    pass
""",
        encoding="utf-8",
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    base = next(symbol for symbol in project.symbols if symbol.name == "Base")
    child = next(symbol for symbol in project.symbols if symbol.name == "Child")

    relationships = [
        relationship
        for relationship in project.relationships
        if relationship.source_id == child.id
        and relationship.target_id == base.id
        and relationship.relationship_type == RelationshipType.INHERITS
    ]

    assert len(relationships) == 1
    assert relationships[0].confidence == 1.0


def test_does_not_create_relationship_for_unresolved_reference(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def main() -> None:
    missing_function()
""",
        encoding="utf-8",
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    assert not any(
        relationship.relationship_type == RelationshipType.REFERENCES
        for relationship in project.relationships
    )


def test_reference_relationship_metadata_is_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def helper() -> None:
    pass


def main() -> None:
    helper()
""",
        encoding="utf-8",
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    helper = next(symbol for symbol in project.symbols if symbol.name == "helper")

    relationship = next(
        relationship
        for relationship in project.relationships
        if relationship.target_id == helper.id
        and relationship.relationship_type == RelationshipType.REFERENCES
    )

    assert relationship.metadata["source"] == "ast"
    assert relationship.metadata["name"] == "helper"
    assert "qualified_name" not in relationship.metadata
    assert "line" in relationship.metadata
