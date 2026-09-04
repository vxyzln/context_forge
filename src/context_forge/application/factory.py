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
from context_forge.provider import ProviderConfig, ProviderFactory
from context_forge.task import (
    TaskGroundingService,
    TaskRepositoryGroundingService,
    TaskUnderstandingService,
    TaskValidator,
)


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


def build_generation_service(
    generation_config: ProviderConfig,
) -> ContextGenerationService:
    task_understanding_config = ProviderConfig(
        provider="deterministic",
        model="deterministic-task",
    )

    return ContextGenerationService(
        engine=build_context_engine(),
        serializer=ContextPackageSerializer(),
        provider=ProviderFactory.create(generation_config),
        task_understanding=TaskUnderstandingService(
            provider=ProviderFactory.create(task_understanding_config),
            config=task_understanding_config,
        ),
        task_validator=TaskValidator(),
        task_grounding=TaskGroundingService(),
        task_repository_grounding=TaskRepositoryGroundingService(),
    )
