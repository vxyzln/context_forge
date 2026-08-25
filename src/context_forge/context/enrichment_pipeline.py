from context_forge.context.enrichment import ContextEnricher
from context_forge.context.models import ContextUnit
from context_forge.models.project import Project


class ContextEnrichmentPipeline:
    def __init__(self, enrichers: list[ContextEnricher]) -> None:
        self.enrichers = tuple(enrichers)

    def enrich(
        self,
        project: Project,
        units: list[ContextUnit],
    ) -> list[ContextUnit]:
        enriched = list(units)

        for enricher in self.enrichers:
            enriched = [enricher.enrich(project, unit) for unit in enriched]
        return enriched
