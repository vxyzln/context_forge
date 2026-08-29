from pathlib import Path
from uuid import UUID

from context_forge.context import (
    ContextAssembler,
    ContextBudgetCompressor,
    ContextCompressionPipeline,
    ContextEnrichmentPipeline,
    ContextPackage,
    ContextPackageBuilder,
    ContextPriorityOrdering,
    ContextRequest,
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
from context_forge.context.depth import ContextDepthSelector
from context_forge.context.models import ContextUnit
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


def make_engine(max_context_units: int = 20) -> DefaultContextEngine:
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


def make_project() -> tuple[Project, File]:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-stage5"),
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

    return project, file


def test_stage5_engine_returns_final_context_package() -> None:
    project, file = make_project()

    package = make_engine().build(
        ContextRequest(
            project=project,
            task="auth",
        )
    )

    assert isinstance(package, ContextPackage)
    assert package.task == "auth"
    assert package.units
    assert package.units[0].entity_id == file.id


def test_stage5_engine_produces_unique_units() -> None:
    project, _ = make_project()

    package = make_engine().build(
        ContextRequest(
            project=project,
            task="auth",
        )
    )

    identities = {(unit.entity_id, unit.unit_type) for unit in package.units}

    assert len(package.units) == len(identities)


def test_stage5_engine_is_deterministic() -> None:
    project, _ = make_project()
    engine = make_engine()

    request = ContextRequest(
        project=project,
        task="auth",
    )

    first = engine.build(request)
    second = engine.build(request)

    assert first == second


def test_stage5_engine_respects_context_budget() -> None:
    project, _ = make_project()

    package = make_engine(max_context_units=1).build(
        ContextRequest(
            project=project,
            task="auth",
        )
    )

    assert len(package.units) <= 1


def test_stage5_engine_preserves_package_task() -> None:
    project, _ = make_project()

    package = make_engine().build(
        ContextRequest(
            project=project,
            task="authentication",
        )
    )

    assert package.task == "authentication"


def test_stage5_assembly_orders_units_deterministically() -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")

    package = ContextPackage(
        task="authentication",
        units=(
            ContextUnit(
                entity_id=second_id,
                unit_type=ContextUnitType.FILE,
                relevance=0.8,
            ),
            ContextUnit(
                entity_id=first_id,
                unit_type=ContextUnitType.FILE,
                relevance=0.8,
            ),
        ),
    )

    assembler = ContextAssembler(
        ContextPriorityOrdering(
            DeterministicPrioritizer(),
        ),
    )

    first = assembler.assemble(package)
    second = assembler.assemble(package)

    assert first == second
    assert len(first.units) == 2


def test_stage5_empty_package_is_valid() -> None:
    package = ContextPackage(
        task="authentication",
        units=(),
    )

    assembler = ContextAssembler(
        ContextPriorityOrdering(
            DeterministicPrioritizer(),
        ),
    )

    result = assembler.assemble(package)

    assert result.task == "authentication"
    assert result.units == ()
