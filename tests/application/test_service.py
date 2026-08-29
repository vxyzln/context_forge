from pathlib import Path

from context_forge.application import ContextGenerationService
from context_forge.context import (
    ContextPackage,
    ContextPackageSerializer,
)
from context_forge.models.project import Project
from context_forge.provider import (
    ContextProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
)


class StubContextEngine:
    def __init__(self, package: ContextPackage) -> None:
        self.package = package
        self.calls: list[tuple[Project, str]] = []

    def build(self, project: Project, task: str) -> ContextPackage:
        self.calls.append((project, task))
        return self.package


class StubProvider(ContextProvider):
    def __init__(self, response: GenerationResponse) -> None:
        self.response = response
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return self.response


def make_project() -> Project:
    return Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )


def make_package() -> ContextPackage:
    return ContextPackage(
        task="authenticate user",
        units=(),
    )


def make_response() -> GenerationResponse:
    return GenerationResponse(
        content="Authentication is handled by auth.py.",
        provider="test",
        model="test-model",
    )


def test_service_builds_context_with_engine() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    config = ProviderConfig(model="test-model")

    service.generate(
        project=project,
        task="authenticate user",
        config=config,
    )

    assert engine.calls == [(project, "authenticate user")]


def test_service_serializes_context_package() -> None:
    project = make_project()
    package = ContextPackage(
        task="authenticate user",
        units=(),
    )
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    config = ProviderConfig(model="test-model")

    service.generate(
        project=project,
        task="authenticate user",
        config=config,
    )

    assert len(provider.requests) == 1
    assert provider.requests[0].context == ('{"task":"authenticate user","units":[]}')


def test_service_builds_provider_request() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    config = ProviderConfig(
        model="test-model",
        temperature=0.5,
        max_tokens=256,
    )

    service.generate(
        project=project,
        task="authenticate user",
        config=config,
    )

    assert len(provider.requests) == 1

    request = provider.requests[0]

    assert request.task == "authenticate user"
    assert request.context == '{"task":"authenticate user","units":[]}'
    assert request.config == config


def test_service_returns_provider_response() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    response = make_response()
    provider = StubProvider(response)

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    result = service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="test-model"),
    )

    assert result is response


def test_service_preserves_provider_errors() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)

    class FailingProvider(ContextProvider):
        def generate(self, request: GenerationRequest) -> GenerationResponse:
            raise RuntimeError("provider failed")

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=FailingProvider(),
    )

    try:
        service.generate(
            project=project,
            task="authenticate user",
            config=ProviderConfig(model="test-model"),
        )
    except RuntimeError as exc:
        assert str(exc) == "provider failed"
    else:
        raise AssertionError("Expected provider error to propagate")


def test_service_passes_config_without_modification() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    config = ProviderConfig(
        model="qwen3:8b",
        temperature=0.0,
        max_tokens=128,
    )

    service.generate(
        project=project,
        task="Explain Context Forge",
        config=config,
    )

    assert provider.requests[0].config is config


def test_service_is_repeatable() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    response = make_response()
    provider = StubProvider(response)

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    config = ProviderConfig(model="test-model")

    first = service.generate(
        project=project,
        task="authenticate user",
        config=config,
    )

    second = service.generate(
        project=project,
        task="authenticate user",
        config=config,
    )

    assert first is response
    assert second is response
    assert len(provider.requests) == 2
    assert provider.requests[0] == provider.requests[1]
