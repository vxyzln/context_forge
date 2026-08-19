from pathlib import Path

from context_forge.extractor.python import PythonExtractor
from context_forge.graph.builder import RelationshipBuilder
from context_forge.scanner.repository import RepositoryScanner


def test_builder_creates_definition_relationships(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    PythonExtractor().extract(project)
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
    PythonExtractor().extract(project)
    RelationshipBuilder().build(project)

    imports = [
        relationship
        for relationship in project.relationships
        if relationship.relationship_type == "imports"
    ]

    assert len(imports) == 1
