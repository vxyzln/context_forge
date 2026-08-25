from pathlib import Path

from context_forge.context.models import ContextUnit
from context_forge.context.relationship_enrichment import (
    RelationshipContextEnricher,
)
from context_forge.context.types import ContextUnitType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship


def test_relationship_enricher_adds_relationship_facts() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    source = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
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

    relationship = Relationship(
        source_id=source.id,
        target_id=target.id,
        relationship_type="imports",
    )
    project.add_relationship(relationship)

    unit = ContextUnit(
        entity_id=source.id,
        unit_type=ContextUnitType.FILE,
        relevance=0.8,
    )

    enriched = RelationshipContextEnricher().enrich(project, unit)

    assert len(enriched.facts) == 1
    assert enriched.facts[0].fact_type == "relationship"
    assert "imports" in enriched.facts[0].value
    assert enriched.facts[0].evidence[0].source_id == relationship.id


def test_relationship_enricher_handles_target_side() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    source = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
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

    relationship = Relationship(
        source_id=source.id,
        target_id=target.id,
        relationship_type="imports",
    )
    project.add_relationship(relationship)

    unit = ContextUnit(
        entity_id=target.id,
        unit_type=ContextUnitType.FILE,
    )

    enriched = RelationshipContextEnricher().enrich(project, unit)

    assert len(enriched.facts) == 1
    assert "imports" in enriched.facts[0].value


def test_relationship_enricher_ignores_unrelated_units() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    source = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
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

    unrelated = File(
        project_id=project.id,
        path=Path("unrelated.py"),
        name="unrelated.py",
        extension=".py",
    )
    project.add_file(unrelated)

    unit = ContextUnit(
        entity_id=unrelated.id,
        unit_type=ContextUnitType.FILE,
    )

    enriched = RelationshipContextEnricher().enrich(project, unit)

    assert enriched == unit
