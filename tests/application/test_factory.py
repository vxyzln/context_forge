from context_forge.application import (
    ContextGenerationService,
    build_context_engine,
    build_generation_service,
)
from context_forge.context import DefaultContextEngine
from context_forge.provider import DeterministicProvider


def test_build_context_engine() -> None:
    engine = build_context_engine()

    assert isinstance(engine, DefaultContextEngine)


def test_build_generation_service() -> None:
    service = build_generation_service()

    assert isinstance(service, ContextGenerationService)
    assert isinstance(service.provider, DeterministicProvider)
    assert service.task_understanding is not None
    assert service.task_validator is not None


def test_build_generation_service_is_independent() -> None:
    first = build_generation_service()
    second = build_generation_service()

    assert first is not second
    assert first.engine is not second.engine
    assert first.provider is not second.provider
