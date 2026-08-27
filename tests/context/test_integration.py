from pathlib import Path

from context_forge.context import (
    ContextAssembler,
    ContextBudgetCompressor,
    ContextCompressionPipeline,
    ContextEnrichmentPipeline,
    ContextPackageBuilder,
    ContextPriorityOrdering,
    ContextSelector,
    ContextUnitType,
    DefaultContextEngine,
    DeterministicContextCompressor,
    DeterministicPrioritizer,
    DeterministicRanker,
    FileContextEnricher,
    GraphExpander,
    RelationshipContextEnricher,
    SymbolContextEnricher,
)
from context_forge.context.candidates import CandidateGenerator
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


def test_context_engine_runs_complete_pipeline() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
        size=128,
    )

    project.add_file(file)

    engine = DefaultContextEngine(
        candidate_generator=CandidateGenerator(),
        ranker=DeterministicRanker(),
        selector=ContextSelector(),
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

    package = engine.build(project, "auth")

    assert package.task == "auth"
    assert len(package.units) == 1
    assert package.units[0].entity_id == file.id
    assert package.units[0].unit_type == ContextUnitType.FILE
    assert package.units[0].facts


def test_context_engine_compresses_duplicate_units() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
        size=128,
    )

    project.add_file(file)

    engine = DefaultContextEngine(
        candidate_generator=CandidateGenerator(),
        ranker=DeterministicRanker(),
        selector=ContextSelector(),
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

    package = engine.build(project, "auth")

    assert package.units
    assert len(package.units) == len(
        {(unit.entity_id, unit.unit_type) for unit in package.units}
    )
