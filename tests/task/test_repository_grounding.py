from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.task.models import (
    GroundedEntity,
    GroundedTask,
    TaskInterpretation,
)
from context_forge.task.repository_grounding import (
    TaskRepositoryGroundingService,
)


def make_project():
    project = Project(
        name="test",
        root_path=Path("/tmp/context-forge-test"),
    )

    file_a = File(
        project_id=project.id,
        path=Path("a.py"),
        name="a.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    file_b = File(
        project_id=project.id,
        path=Path("b.py"),
        name="b.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    file_c = File(
        project_id=project.id,
        path=Path("c.py"),
        name="c.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(file_a)
    project.add_file(file_b)
    project.add_file(file_c)

    symbol_a = Symbol(
        file_id=file_a.id,
        name="SymbolA",
        qualified_name="SymbolA",
        kind="class",
        start_line=1,
        end_line=10,
    )

    symbol_b = Symbol(
        file_id=file_b.id,
        name="SymbolB",
        qualified_name="SymbolB",
        kind="class",
        start_line=1,
        end_line=10,
    )

    symbol_c = Symbol(
        file_id=file_c.id,
        name="SymbolC",
        qualified_name="SymbolC",
        kind="class",
        start_line=1,
        end_line=10,
    )

    project.add_symbol(symbol_a)
    project.add_symbol(symbol_b)
    project.add_symbol(symbol_c)

    return (
        project,
        file_a,
        file_b,
        file_c,
        symbol_a,
        symbol_b,
        symbol_c,
    )


def make_grounded_task(entity_id):
    interpretation = TaskInterpretation(
        task="Fix ServiceA",
        intent="fix",
        target="ServiceA",
        concepts=("service",),
        requested_action="fix",
    )

    return GroundedTask(
        interpretation=interpretation,
        entities=(
            GroundedEntity(
                entity_id=entity_id,
                entity_type="symbol",
                reference="ServiceA",
                confidence=1.0,
                provenance="exact symbol qualified name",
            ),
        ),
    )


def test_grounds_direct_entity_relationship():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        _symbol_c,
    ) = make_project()

    relationship = Relationship(
        source_id=symbol_a.id,
        target_id=symbol_b.id,
        relationship_type=RelationshipType.REFERENCES,
        confidence=0.9,
    )
    project.add_relationship(relationship)

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService().ground(
        project,
        task,
    )

    assert result.task == task
    assert result.related_entity_ids == (symbol_b.id,)
    assert len(result.relationships) == 1

    grounded_relationship = result.relationships[0]

    assert grounded_relationship.source_id == symbol_a.id
    assert grounded_relationship.target_id == symbol_b.id
    assert grounded_relationship.relationship_type == RelationshipType.REFERENCES
    assert grounded_relationship.depth == 1
    assert grounded_relationship.confidence == 0.9
    assert grounded_relationship.provenance == ("repository relationship traversal")


def test_grounding_follows_incoming_and_outgoing_relationships():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        symbol_c,
    ) = make_project()

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=symbol_c.id,
            target_id=symbol_a.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService().ground(
        project,
        task,
    )

    assert set(result.related_entity_ids) == {
        symbol_b.id,
        symbol_c.id,
    }


def test_grounding_supports_multiple_depths():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        symbol_c,
    ) = make_project()

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=symbol_b.id,
            target_id=symbol_c.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService(max_depth=2).ground(
        project,
        task,
    )

    assert result.related_entity_ids == (
        symbol_b.id,
        symbol_c.id,
    )

    assert [relationship.depth for relationship in result.relationships] == [
        1,
        2,
    ]


def test_grounding_is_cycle_safe():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        symbol_c,
    ) = make_project()

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=symbol_b.id,
            target_id=symbol_c.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=symbol_c.id,
            target_id=symbol_a.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService(max_depth=10).ground(
        project,
        task,
    )

    assert set(result.related_entity_ids) == {
        symbol_b.id,
        symbol_c.id,
    }

    assert symbol_a.id not in result.related_entity_ids


def test_grounding_does_not_duplicate_entities():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        symbol_c,
    ) = make_project()

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_c.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=symbol_b.id,
            target_id=symbol_c.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService(max_depth=2).ground(
        project,
        task,
    )

    assert result.related_entity_ids.count(symbol_c.id) == 1


def test_grounding_excludes_direct_entities():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        _symbol_c,
    ) = make_project()

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService().ground(
        project,
        task,
    )

    assert symbol_a.id not in result.related_entity_ids


def test_grounding_depth_zero_returns_no_related_entities():
    (
        project,
        _file_a,
        _file_b,
        _file_c,
        symbol_a,
        symbol_b,
        _symbol_c,
    ) = make_project()

    project.add_relationship(
        Relationship(
            source_id=symbol_a.id,
            target_id=symbol_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    task = make_grounded_task(symbol_a.id)

    result = TaskRepositoryGroundingService().ground(
        project,
        task,
        max_depth=0,
    )

    assert result.related_entity_ids == ()
    assert result.relationships == ()
    assert result.max_depth == 0


def test_grounding_rejects_negative_depth():
    with pytest.raises(ValueError, match="cannot be negative"):
        TaskRepositoryGroundingService(max_depth=-1)


def test_grounding_rejects_negative_depth_override():
    project, *_ = make_project()
    task = make_grounded_task(uuid4())

    with pytest.raises(ValueError, match="cannot be negative"):
        TaskRepositoryGroundingService().ground(
            project,
            task,
            max_depth=-1,
        )


def test_empty_grounded_task_produces_empty_repository_grounding():
    project, *_ = make_project()

    interpretation = TaskInterpretation(
        task="Fix authentication",
        intent="fix",
        target=None,
    )

    task = GroundedTask(
        interpretation=interpretation,
    )

    result = TaskRepositoryGroundingService().ground(
        project,
        task,
    )

    assert result.task == task
    assert result.related_entity_ids == ()
    assert result.relationships == ()


def test_grounded_relationship_rejects_invalid_depth():
    from context_forge.task.models import GroundedRelationship

    with pytest.raises(ValueError, match="depth must be positive"):
        GroundedRelationship(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=RelationshipType.REFERENCES,
            depth=0,
            confidence=1.0,
            provenance="test",
        )


def test_grounded_relationship_rejects_invalid_confidence():
    from context_forge.task.models import GroundedRelationship

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        GroundedRelationship(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=RelationshipType.REFERENCES,
            depth=1,
            confidence=1.1,
            provenance="test",
        )


def test_grounded_relationship_rejects_empty_provenance():
    from context_forge.task.models import GroundedRelationship

    with pytest.raises(ValueError, match="cannot be empty"):
        GroundedRelationship(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=RelationshipType.REFERENCES,
            depth=1,
            confidence=1.0,
            provenance=" ",
        )


def test_repository_grounding_rejects_negative_depth():
    from context_forge.task.models import RepositoryGrounding

    _, *_ = make_project()
    task = make_grounded_task(uuid4())

    with pytest.raises(ValueError, match="cannot be negative"):
        RepositoryGrounding(
            task=task,
            max_depth=-1,
        )
