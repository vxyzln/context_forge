from context_forge.application.service import RepositoryContextService
from context_forge.context import (
    CandidateGenerator,
    ContextAssembler,
    ContextBudgetCompressor,
    ContextCompressionPipeline,
    ContextEnrichmentPipeline,
    ContextPackageBuilder,
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
from context_forge.task import (
    TaskGroundingService,
    TaskRepositoryGroundingService,
    TaskUnderstandingService,
    TaskValidator,
)


def build_context_engine(
    max_context_units: int = 20,
) -> DefaultContextEngine:
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
        max_context_units=max_context_units,
    )


def build_context_service(
    max_context_units: int = 20,
) -> RepositoryContextService:
    engine = build_context_engine(max_context_units=max_context_units)
    return RepositoryContextService(
        engine=engine,
        task_understanding=TaskUnderstandingService(),
        task_validator=TaskValidator(),
        task_grounding=TaskGroundingService(),
        task_repository_grounding=TaskRepositoryGroundingService(),
    )
