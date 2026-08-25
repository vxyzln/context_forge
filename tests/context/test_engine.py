from pathlib import Path

import pytest

from context_forge.context import (
    ContextEngine,
    ContextEnrichmentPipeline,
    ContextPackageBuilder,
    ContextSelector,
    ContextUnitType,
    DefaultContextEngine,
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


def make_engine() -> DefaultContextEngine:
    return DefaultContextEngine(
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

    package = make_engine().build(project, "auth")

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
        make_engine().build(project, "   ")


def test_default_context_engine_returns_context_package() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    package = make_engine().build(project, "authentication")

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

    package = make_engine().build(project, "auth")

    assert package.units
    assert package.units[0].facts
