from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.expansion import GraphExpander
from context_forge.context.types import ContextUnitType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship


def make_project() -> tuple[Project, File, File, File]:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    first = File(
        project_id=project.id,
        path=Path("src/first.py"),
        name="first.py",
        extension=".py",
    )
    second = File(
        project_id=project.id,
        path=Path("src/second.py"),
        name="second.py",
        extension=".py",
    )
    third = File(
        project_id=project.id,
        path=Path("src/third.py"),
        name="third.py",
        extension=".py",
    )

    project.add_file(first)
    project.add_file(second)
    project.add_file(third)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
        )
    )
    project.add_relationship(
        Relationship(
            source_id=second.id,
            target_id=third.id,
            relationship_type="imports",
        )
    )

    return project, first, second, third


def make_candidate(file: File) -> ContextCandidate:
    return ContextCandidate(
        entity_id=file.id,
        unit_type=ContextUnitType.FILE,
        score=1.0,
        source="deterministic_search",
    )


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


def test_graph_expander_expands_multiple_levels() -> None:
    project, first, second, third = make_project()

    expansions = GraphExpander(max_depth=2).expand(
        project,
        [make_candidate(first)],
    )

    related_ids = [candidate.entity_id for candidate in expansions[0].related]

    assert second.id in related_ids
    assert third.id in related_ids
    assert len(related_ids) == 2


def test_graph_expander_zero_depth_returns_no_related_entities() -> None:
    project, first, _, _ = make_project()

    expansions = GraphExpander(max_depth=0).expand(
        project,
        [make_candidate(first)],
    )

    assert expansions[0].related == ()


def test_graph_expander_does_not_repeat_entities_across_depths() -> None:
    project, first, _, third = make_project()

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=third.id,
            relationship_type="imports",
        )
    )

    expansions = GraphExpander(max_depth=2).expand(
        project,
        [make_candidate(first)],
    )

    related_ids = [candidate.entity_id for candidate in expansions[0].related]

    assert related_ids.count(third.id) == 1
    assert len(related_ids) == 2


def test_graph_expander_handles_cycles() -> None:
    project, first, second, third = make_project()

    project.add_relationship(
        Relationship(
            source_id=third.id,
            target_id=first.id,
            relationship_type="imports",
        )
    )

    expansions = GraphExpander(max_depth=3).expand(
        project,
        [make_candidate(first)],
    )

    related_ids = [candidate.entity_id for candidate in expansions[0].related]

    assert first.id not in related_ids
    assert related_ids.count(second.id) == 1
    assert related_ids.count(third.id) == 1


def test_graph_expander_is_deterministic() -> None:
    project, first, _, _ = make_project()

    first_result = GraphExpander(max_depth=2).expand(
        project,
        [make_candidate(first)],
    )
    second_result = GraphExpander(max_depth=2).expand(
        project,
        [make_candidate(first)],
    )

    assert first_result == second_result


def test_graph_expander_rejects_negative_depth() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        GraphExpander(max_depth=-1)


def test_graph_expander_preserves_candidate() -> None:
    project, first, _, _ = make_project()
    candidate = make_candidate(first)

    expansions = GraphExpander(max_depth=1).expand(
        project,
        [candidate],
    )

    assert expansions[0].candidate == candidate


def test_graph_expander_uses_depth_override() -> None:
    project, first, second, third = make_project()

    expansions = GraphExpander(max_depth=0).expand(
        project,
        [make_candidate(first)],
        max_depth=2,
    )

    related_ids = [candidate.entity_id for candidate in expansions[0].related]

    assert second.id in related_ids
    assert third.id in related_ids


def test_graph_expander_depth_override_can_disable_expansion() -> None:
    project, first, _, _ = make_project()

    expansions = GraphExpander(max_depth=2).expand(
        project,
        [make_candidate(first)],
        max_depth=0,
    )

    assert expansions[0].related == ()


def test_graph_expander_rejects_negative_depth_override() -> None:
    project, first, _, _ = make_project()

    with pytest.raises(ValueError, match="cannot be negative"):
        GraphExpander().expand(
            project,
            [make_candidate(first)],
            max_depth=-1,
        )
