from abc import ABC, abstractmethod

from context_forge.context.assembly import ContextAssembler
from context_forge.context.candidates import CandidateGenerator
from context_forge.context.compression_pipeline import ContextCompressionPipeline
from context_forge.context.enrichment_pipeline import ContextEnrichmentPipeline
from context_forge.context.expansion import GraphExpander
from context_forge.context.models import ContextPackage
from context_forge.context.package import ContextPackageBuilder
from context_forge.context.ranking import DeterministicRanker
from context_forge.context.selection import ContextSelector
from context_forge.models.project import Project


class ContextEngine(ABC):
    @abstractmethod
    def build(self, project: Project, task: str) -> ContextPackage:
        """Build a context package for a project task."""
        raise NotImplementedError


class DefaultContextEngine(ContextEngine):
    def __init__(
        self,
        candidate_generator: CandidateGenerator,
        ranker: DeterministicRanker,
        selector: ContextSelector,
        expander: GraphExpander,
        package_builder: ContextPackageBuilder,
        enrichment_pipeline: ContextEnrichmentPipeline,
        compression_pipeline: ContextCompressionPipeline,
        assembly: ContextAssembler,
        max_context_units: int = 20,
    ) -> None:
        self.candidate_generator = candidate_generator
        self.ranker = ranker
        self.selector = selector
        self.expander = expander
        self.package_builder = package_builder
        self.enrichment_pipeline = enrichment_pipeline
        self.compression_pipeline = compression_pipeline
        self.assembly = assembly
        self.max_context_units = max_context_units

    def build(self, project: Project, task: str) -> ContextPackage:
        if not task.strip():
            raise ValueError("Task cannot be empty")

        candidates, signals = self.candidate_generator.generate(
            project,
            task,
        )

        ranked = self.ranker.rank(candidates, signals)

        selected = self.selector.select(ranked)

        expanded = self.expander.expand(project, selected)

        selected_signals = {
            candidate.entity_id: signals[candidate.entity_id]
            for candidate in selected
            if candidate.entity_id in signals
        }

        package = self.package_builder.build(
            task,
            expanded,
            selected_signals,
        )

        enriched_units = self.enrichment_pipeline.enrich(
            project,
            list(package.units),
        )

        enriched_package = ContextPackage(
            task=package.task,
            units=tuple(enriched_units),
        )

        compressed = self.compression_pipeline.compress(
            enriched_package,
            max_units=self.max_context_units,
        )

        return self.assembly.assemble(compressed)
