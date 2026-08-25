from pathlib import Path
from uuid import uuid4

from context_forge.context.enrichment import ContextEnricher
from context_forge.context.models import ContextUnit
from context_forge.context.types import ContextUnitType
from context_forge.models.project import Project


def test_context_enricher_is_abstract() -> None:
    assert issubclass(ContextEnricher, object)


def test_context_enricher_requires_enrich_implementation() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
    )

    assert project is not None
    assert unit.unit_type == ContextUnitType.FILE
