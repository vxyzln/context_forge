from pathlib import Path

import pytest

from context_forge.application import ContextGenerationService
from context_forge.context import (
    ContextPackage,
    ContextPackageSerializer,
)
from context_forge.context.request import ContextRequest
from context_forge.models.project import Project
from context_forge.provider import (
    ContextProvider,
    DeterministicProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
)
from context_forge.task import (
    GroundedTask,
    RepositoryGrounding,
    TaskInterpretation,
    TaskState,
    TaskValidation,
)


class StubContextEngine:
    def __init__(self, package: ContextPackage) -> None:
        self.package = package
        self.calls: list[ContextRequest] = []

    def build(self, request: ContextRequest) -> ContextPackage:
        self.calls.append(request)
        return self.package


class StubTaskRepositoryGrounding:
    def __init__(self, grounding):
        self.grounding = grounding
        self.calls = []

    def ground(self, project, task):
        self.calls.append((project, task))
        return self.grounding


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

    assert engine.calls == [
        ContextRequest(
            project=project,
            task="authenticate user",
        )
    ]


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
        model="qwen2.5-coder:7b",
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


def test_service_integrates_with_deterministic_provider() -> None:
    project = make_project()

    package = ContextPackage(
        task="authenticate user",
        units=(),
    )

    engine = StubContextEngine(package)

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=DeterministicProvider(),
    )

    response = service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="deterministic-test"),
    )

    assert response.provider == "deterministic"
    assert response.model == "deterministic-test"
    assert response.content.startswith("Task: authenticate user")
    assert "Context received:" in response.content


class StubTaskUnderstanding:
    def __init__(self, interpretation: TaskInterpretation) -> None:
        self.interpretation = interpretation
        self.tasks: list[str] = []

    def understand(self, task: str) -> TaskInterpretation:
        self.tasks.append(task)
        return self.interpretation


class StubTaskValidator:
    def __init__(self, validation: TaskValidation) -> None:
        self.validation = validation
        self.interpretations: list[TaskInterpretation] = []

    def validate(
        self,
        interpretation: TaskInterpretation,
    ) -> TaskValidation:
        self.interpretations.append(interpretation)
        return self.validation


class StubTaskGrounding:
    def __init__(self, grounding: GroundedTask) -> None:
        self.grounding = grounding
        self.projects: list[Project] = []
        self.interpretations: list[TaskInterpretation] = []

    def ground(
        self,
        project: Project,
        interpretation: TaskInterpretation,
    ) -> GroundedTask:
        self.projects.append(project)
        self.interpretations.append(interpretation)
        return self.grounding


def make_task_interpretation() -> TaskInterpretation:
    return TaskInterpretation(
        task="authenticate user",
        intent="feature",
        target="authentication",
        concepts=("authentication",),
        requested_action="implement",
        constraints=(),
        ambiguity=None,
    )


def test_service_validates_task_before_building_context() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    interpretation = make_task_interpretation()
    understanding = StubTaskUnderstanding(interpretation)
    validator = StubTaskValidator(TaskValidation(state=TaskState.CLEAR))

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
    )

    service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="test-model"),
    )

    assert understanding.tasks == ["authenticate user"]
    assert validator.interpretations == [interpretation]


def test_service_passes_repository_grounding_to_context_request() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    interpretation = make_task_interpretation()

    grounded_task = GroundedTask(
        interpretation=interpretation,
    )

    repository_grounding = RepositoryGrounding(
        task=grounded_task,
    )

    understanding = StubTaskUnderstanding(interpretation)
    validator = StubTaskValidator(
        TaskValidation(state=TaskState.CLEAR),
    )
    task_grounding = StubTaskGrounding(grounded_task)
    task_repository_grounding = StubTaskRepositoryGrounding(
        repository_grounding,
    )

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
        task_grounding=task_grounding,
        task_repository_grounding=task_repository_grounding,
    )

    service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="test-model"),
    )

    assert task_grounding.projects == [project]
    assert task_grounding.interpretations == [interpretation]
    assert task_repository_grounding.calls == [(project, grounded_task)]
    assert engine.calls == [
        ContextRequest(
            project=project,
            task="authenticate user",
            interpretation=interpretation,
            grounding=repository_grounding,
        )
    ]


def test_service_does_not_ground_invalid_task() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    interpretation = make_task_interpretation()
    understanding = StubTaskUnderstanding(interpretation)
    validator = StubTaskValidator(
        TaskValidation(
            state=TaskState.AMBIGUOUS,
            reasons=("target is unclear",),
        )
    )
    task_grounding = StubTaskGrounding(
        GroundedTask(interpretation=interpretation),
    )

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
        task_grounding=task_grounding,
    )

    try:
        service.generate(
            project=project,
            task="authenticate user",
            config=ProviderConfig(model="test-model"),
        )
    except ValueError as exc:
        assert str(exc) == "task validation failed: ambiguous"
    else:
        raise AssertionError("Expected ValueError")

    assert task_grounding.projects == []
    assert task_grounding.interpretations == []
    assert engine.calls == []
    assert provider.requests == []


def test_service_rejects_ambiguous_task_before_context_generation() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    understanding = StubTaskUnderstanding(make_task_interpretation())
    validator = StubTaskValidator(
        TaskValidation(
            state=TaskState.AMBIGUOUS,
            reasons=("target is unclear",),
        )
    )

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
    )

    try:
        service.generate(
            project=project,
            task="authenticate user",
            config=ProviderConfig(model="test-model"),
        )
    except ValueError as exc:
        assert str(exc) == "task validation failed: ambiguous"
    else:
        raise AssertionError("Expected ValueError")

    assert engine.calls == []
    assert provider.requests == []


def test_service_rejects_insufficient_task_before_context_generation() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    understanding = StubTaskUnderstanding(make_task_interpretation())
    validator = StubTaskValidator(
        TaskValidation(
            state=TaskState.INSUFFICIENT,
            reasons=("task intent is missing",),
        )
    )

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
    )

    try:
        service.generate(
            project=project,
            task="authenticate user",
            config=ProviderConfig(model="test-model"),
        )
    except ValueError as exc:
        assert str(exc) == "task validation failed: insufficient"
    else:
        raise AssertionError("Expected ValueError")

    assert engine.calls == []
    assert provider.requests == []


def test_service_passes_task_interpretation_to_context_engine() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    interpretation = make_task_interpretation()
    understanding = StubTaskUnderstanding(interpretation)
    validator = StubTaskValidator(TaskValidation(state=TaskState.CLEAR))

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
    )

    service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="test-model"),
    )

    assert engine.calls == [
        ContextRequest(
            project=project,
            task="authenticate user",
            interpretation=interpretation,
        )
    ]


def test_service_builds_generation_prompt_before_provider() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
    )

    service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="test-model"),
    )

    assert provider.requests[0].prompt == (
        "Use the following task and project context to answer "
        "the user's request.\n\n"
        "Task:\nauthenticate user\n\n"
        'Context:\n{"task":"authenticate user","units":[]}'
    )


def test_service_does_not_repository_ground_invalid_task() -> None:
    project = make_project()
    package = make_package()
    engine = StubContextEngine(package)
    provider = StubProvider(make_response())

    interpretation = make_task_interpretation()
    grounded_task = GroundedTask(
        interpretation=interpretation,
    )

    understanding = StubTaskUnderstanding(interpretation)
    validator = StubTaskValidator(
        TaskValidation(
            state=TaskState.AMBIGUOUS,
            reasons=("target is unclear",),
        )
    )
    task_grounding = StubTaskGrounding(grounded_task)
    repository_grounding_service = StubTaskRepositoryGrounding(
        RepositoryGrounding(task=grounded_task),
    )

    service = ContextGenerationService(
        engine=engine,
        serializer=ContextPackageSerializer(),
        provider=provider,
        task_understanding=understanding,
        task_validator=validator,
        task_grounding=task_grounding,
        task_repository_grounding=repository_grounding_service,
    )

    with pytest.raises(
        ValueError,
        match="task validation failed: ambiguous",
    ):
        service.generate(
            project=project,
            task="authenticate user",
            config=ProviderConfig(model="test-model"),
        )

    assert task_grounding.projects == []
    assert task_grounding.interpretations == []
    assert repository_grounding_service.calls == []
    assert engine.calls == []
    assert provider.requests == []
