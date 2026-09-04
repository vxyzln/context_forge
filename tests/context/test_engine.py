from pathlib import Path

import pytest

from context_forge.context import (
    ContextAssembler,
    ContextBudgetCompressor,
    ContextCompressionPipeline,
    ContextEngine,
    ContextEnrichmentPipeline,
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
from context_forge.context.candidate import ContextCandidate
from context_forge.context.candidates import CandidateGenerator
from context_forge.context.depth import (
    ContextDepth,
    ContextDepthDecision,
    ContextDepthSelector,
)
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.task import (
    GroundedTask,
    RepositoryGrounding,
    TaskInterpretation,
)


class RecordingCandidateGenerator:
    def __init__(self, candidates=None):
        self.calls = []
        self.candidates = candidates or []

    def generate(
        self,
        project,
        task,
        interpretation=None,
        grounding=None,
    ):
        self.calls.append(
            {
                "project": project,
                "task": task,
                "interpretation": interpretation,
                "grounding": grounding,
            }
        )
        return self.candidates, {}


class FixedDepthSelector:
    def __init__(self, decision: ContextDepthDecision) -> None:
        self.decision = decision

    def select(
        self,
        candidates: list[ContextCandidate],
    ) -> ContextDepthDecision:
        return self.decision


def make_engine() -> DefaultContextEngine:
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


def test_context_engine_is_abstract() -> None:
    assert issubclass(ContextEngine, object)


def test_default_context_engine_builds_context_from_project() -> None:
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
    )

    project.add_file(file)

    package = make_engine().build(
        ContextRequest(
            project=project,
            task="auth",
        )
    )
    assert package.task == "auth"
    assert len(package.units) == 1
    assert package.units[0].entity_id == file.id
    assert package.units[0].unit_type == ContextUnitType.FILE


def test_default_context_engine_rejects_empty_task() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    with pytest.raises(ValueError, match="Task cannot be empty"):
        make_engine().build(
            ContextRequest(
                project=project,
                task="   ",
            )
        )


def test_default_context_engine_returns_context_package() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    package = make_engine().build(
        ContextRequest(
            project=project,
            task="authentication",
        )
    )

    assert package.task == "authentication"
    assert isinstance(package.units, tuple)


def test_context_engine_enriches_package_units() -> None:
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

    package = make_engine().build(
        ContextRequest(
            project=project,
            task="auth",
        )
    )

    assert package.units
    assert package.units[0].facts


def test_context_engine_returns_deterministically_assembled_package() -> None:
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

    engine = make_engine()

    request = ContextRequest(
        project=project,
        task="auth",
    )

    first = engine.build(request)
    second = engine.build(request)

    assert first == second
    assert first.task == "auth"
    assert first.units


def test_default_context_engine_uses_selected_context_depth() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    third = File(
        project_id=project.id,
        path=Path("third.py"),
        name="third.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)
    project.add_file(third)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
        )
    )

    project.add_relationship(
        Relationship(
            source_id=second.id,
            target_id=third.id,
            relationship_type="imports",
        )
    )

    engine = DefaultContextEngine(
        candidate_generator=CandidateGenerator(),
        ranker=DeterministicRanker(),
        selector=ContextSelector(),
        depth_selector=FixedDepthSelector(
            ContextDepthDecision(
                depth=2,
                mode=ContextDepth.DEEP,
                reason="test depth",
            )
        ),
        expander=GraphExpander(max_depth=0),
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

    package = engine.build(
        ContextRequest(
            project=project,
            task="first",
        )
    )

    entity_ids = {unit.entity_id for unit in package.units}

    assert first.id in entity_ids
    assert second.id in entity_ids
    assert third.id in entity_ids


def test_engine_passes_repository_grounding_to_candidate_generator() -> None:
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
    )

    project.add_file(file)

    candidate_generator = RecordingCandidateGenerator(
        candidates=[
            ContextCandidate(
                entity_id=file.id,
                unit_type=ContextUnitType.FILE,
                score=1.0,
                source="task_grounding",
                reason="test",
            )
        ]
    )

    engine = DefaultContextEngine(
        candidate_generator=candidate_generator,
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

    interpretation = TaskInterpretation(
        task="Fix authentication",
        intent="fix",
        target="AuthenticationService",
    )

    grounded_task = GroundedTask(
        interpretation=interpretation,
    )

    grounding = RepositoryGrounding(
        task=grounded_task,
    )

    request = ContextRequest(
        project=project,
        task="Fix authentication",
        interpretation=interpretation,
        grounding=grounding,
    )

    engine.build(request)

    assert len(candidate_generator.calls) == 1
    assert candidate_generator.calls[0]["project"] is project
    assert candidate_generator.calls[0]["task"] == "Fix authentication"
    assert candidate_generator.calls[0]["interpretation"] is interpretation
    assert candidate_generator.calls[0]["grounding"] is grounding
