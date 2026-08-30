from context_forge.application.service import ContextGenerationService
from context_forge.context import (
    CandidateGenerator,
    ContextAssembler,
    ContextBudgetCompressor,
    ContextCompressionPipeline,
    ContextEnrichmentPipeline,
    ContextPackageBuilder,
    ContextPackageSerializer,
    ContextPriorityOrdering,
    ContextSelector,
    DefaultContextEngine,
    DeterministicContextCompressor,
    DeterministicPrioritizer,
    DeterministicRanker,
    FileContextEnricher,
    GraphExpander,
    RelationshipContextEnricher,
    SymbolContextEnricher,
)
from context_forge.context.depth import ContextDepthSelector
from context_forge.provider import DeterministicProvider, ProviderConfig
from context_forge.task import TaskUnderstandingService, TaskValidator


def build_context_engine() -> DefaultContextEngine:
    return DefaultContextEngine(
        candidate_generator=CandidateGenerator(),
        ranker=DeterministicRanker(),
        selector=ContextSelector(),
        depth_selector=ContextDepthSelector(),
        expander=GraphExpander(),
        package_builder=ContextPackageBuilder(),
        enrichment_pipeline=ContextEnrichmentPipeline(
            enrichers=[
                FileContextEnricher(),
                SymbolContextEnricher(),
                RelationshipContextEnricher(),
            ],
        ),
        compression_pipeline=ContextCompressionPipeline(
            compressor=DeterministicContextCompressor(),
            budget_compressor=ContextBudgetCompressor(),
        ),
        assembly=ContextAssembler(
            ContextPriorityOrdering(
                DeterministicPrioritizer(),
            ),
        ),
    )


def build_generation_service() -> ContextGenerationService:
    return ContextGenerationService(
        engine=build_context_engine(),
        serializer=ContextPackageSerializer(),
        provider=DeterministicProvider(),
        task_understanding=TaskUnderstandingService(
            provider=DeterministicProvider(),
            config=ProviderConfig(model="deterministic-task"),
        ),
        task_validator=TaskValidator(),
    )
