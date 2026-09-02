import json
from pathlib import Path

from context_forge.application import build_generation_service
from context_forge.application.service import ContextGenerationService
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
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.models.project import Project
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.provider import (
    ContextProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
    ProviderUsage,
)


class CapturingProvider(ContextProvider):
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)

        return GenerationResponse(
            content="captured response",
            provider="capturing",
            model=request.config.model,
            usage=ProviderUsage(),
            metadata={"mode": "test"},
        )


def test_generation_service_runs_end_to_end() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    service = build_generation_service(
        ProviderConfig(
            provider="deterministic",
            model="deterministic",
        )
    )

    response = service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="deterministic"),
    )

    assert response.provider == "deterministic"
    assert response.model == "deterministic"
    assert response.content.startswith("Task: authenticate user")
    assert "Context received:" in response.content


def test_generation_service_rejects_empty_task() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    service = build_generation_service(
        ProviderConfig(
            provider="deterministic",
            model="deterministic",
        )
    )

    try:
        service.generate(
            project=project,
            task="   ",
            config=ProviderConfig(model="deterministic"),
        )
    except ValueError as exc:
        assert str(exc) == "task must not be empty"
    else:
        raise AssertionError("Expected ValueError")


def test_generation_service_passes_analyzed_context_to_provider(
    tmp_path: Path,
) -> None:
    app_directory = tmp_path / "app"
    app_directory.mkdir()

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    calculator_source = """
    class Calculator:
        def add(self, a, b):
            return a + b
    """

    (app_directory / "calculator.py").write_text(
        calculator_source,
        encoding="utf-8",
    )

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    calculator_file = next(
        file for file in project.files if file.name == "calculator.py"
    )

    provider = CapturingProvider()

    engine = DefaultContextEngine(
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

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    response = service.generate(
        project=project,
        task="calculator.py",
        config=ProviderConfig(
            provider="deterministic",
            model="test-model",
        ),
    )

    assert response.content == "captured response"
    assert response.provider == "capturing"
    assert response.model == "test-model"

    assert len(provider.requests) == 1

    request = provider.requests[0]

    assert request.task == "calculator.py"
    assert request.config.model == "test-model"
    assert request.context

    payload = json.loads(request.context)

    assert payload["task"] == "calculator.py"
    assert payload["units"]

    context_entity_ids = {unit["entity_id"] for unit in payload["units"]}

    assert str(calculator_file.id) in context_entity_ids
    calculator_units = [
    unit
    for unit in payload["units"]
    if unit["entity_id"] == str(calculator_file.id)
]

    assert calculator_units
    assert any(
        unit["content"] == calculator_source
        for unit in calculator_units
    )


def test_generation_service_runs_real_python_project_with_deterministic_provider(
    tmp_path: Path,
) -> None:
    app_directory = tmp_path / "app"
    app_directory.mkdir()

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    (app_directory / "auth.py").write_text(
        """
def authenticate(username, password):
    return username == "admin" and password == "secret"
""",
        encoding="utf-8",
    )

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    assert project.files
    assert any(file.name == "auth.py" for file in project.files)
    assert any(symbol.name == "authenticate" for symbol in project.symbols)

    service = build_generation_service(
        ProviderConfig(
            provider="deterministic",
            model="deterministic-test",
        )
    )

    response = service.generate(
        project=project,
        task="Explain the authenticate function",
        config=ProviderConfig(
            provider="deterministic",
            model="deterministic-test",
        ),
    )

    assert response.provider == "deterministic"
    assert response.model == "deterministic-test"
    assert response.content
    assert "Explain the authenticate function" in response.content
