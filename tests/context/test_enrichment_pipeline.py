from pathlib import Path
from uuid import uuid4

from context_forge.context.enrichment import ContextEnricher
from context_forge.context.enrichment_pipeline import ContextEnrichmentPipeline
from context_forge.context.models import ContextUnit
from context_forge.context.types import ContextUnitType
from context_forge.models.project import Project


class TestEnricher(ContextEnricher):
    def enrich(
        self,
        project: Project,
        unit: ContextUnit,
    ) -> ContextUnit:
        return ContextUnit(
            entity_id=unit.entity_id,
            unit_type=unit.unit_type,
            relevance=unit.relevance,
            signals=unit.signals,
            facts=unit.facts,
            inferences=unit.inferences,
        )


def test_enrichment_pipeline_runs_all_enrichers() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        relevance=0.8,
    )

    pipeline = ContextEnrichmentPipeline(
        enrichers=[TestEnricher(), TestEnricher()],
    )

    result = pipeline.enrich(project, [unit])

    assert len(result) == 1
    assert result[0].entity_id == unit.entity_id
    assert result[0].unit_type == ContextUnitType.FILE
    assert result[0].relevance == 0.8
