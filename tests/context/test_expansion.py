from pathlib import Path
from uuid import uuid4

from context_forge.context.candidate import ContextCandidate
from context_forge.context.expansion import GraphExpander
from context_forge.context.types import ContextUnitType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship


def test_graph_expander_finds_related_entities() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    source = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    target = File(
        project_id=project.id,
        path=Path("database.py"),
        name="database.py",
        extension=".py",
    )

    project.add_file(source)
    project.add_file(target)

    project.add_relationship(
        Relationship(
            source_id=source.id,
            target_id=target.id,
            relationship_type="imports",
        )
    )

    candidate = ContextCandidate(
        entity_id=source.id,
        unit_type=ContextUnitType.FILE,
        score=0.9,
        source="deterministic_search",
    )

    expansions = GraphExpander().expand(project, [candidate])

    assert len(expansions) == 1
    assert expansions[0].candidate == candidate
    assert len(expansions[0].related) == 1
    assert expansions[0].related[0].entity_id == target.id
    assert expansions[0].related[0].unit_type == ContextUnitType.FILE
    assert expansions[0].related[0].source == "graph_expansion"


def test_graph_expander_handles_relationship_in_either_direction() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    source = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    target = File(
        project_id=project.id,
        path=Path("database.py"),
        name="database.py",
        extension=".py",
    )

    project.add_file(source)
    project.add_file(target)

    project.add_relationship(
        Relationship(
            source_id=target.id,
            target_id=source.id,
            relationship_type="imports",
        )
    )

    candidate = ContextCandidate(
        entity_id=source.id,
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
    )

    expansions = GraphExpander().expand(project, [candidate])

    assert len(expansions[0].related) == 1
    assert expansions[0].related[0].entity_id == target.id


def test_graph_expander_ignores_unrelated_entities() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    file = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )

    project.add_file(file)

    candidate = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
    )

    expansions = GraphExpander().expand(project, [candidate])

    assert len(expansions) == 1
    assert expansions[0].related == ()


def test_graph_expander_does_not_duplicate_related_entities() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    source = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    target = File(
        project_id=project.id,
        path=Path("database.py"),
        name="database.py",
        extension=".py",
    )

    project.add_file(source)
    project.add_file(target)

    project.add_relationship(
        Relationship(
            source_id=source.id,
            target_id=target.id,
            relationship_type="imports",
        )
    )
    project.add_relationship(
        Relationship(
            source_id=source.id,
            target_id=target.id,
            relationship_type="imports",
        )
    )

    candidate = ContextCandidate(
        entity_id=source.id,
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
    )

    expansions = GraphExpander().expand(project, [candidate])

    assert len(expansions[0].related) == 1
