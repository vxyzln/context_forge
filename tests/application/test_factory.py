from context_forge.application import (
    RepositoryContextService,
    build_context_engine,
    build_context_service,
)
from context_forge.context import DefaultContextEngine


def test_build_context_engine() -> None:
    engine = build_context_engine()

    assert isinstance(engine, DefaultContextEngine)
    assert engine.max_context_units == 20


def test_build_context_engine_custom_budget() -> None:
    engine = build_context_engine(max_context_units=50)

    assert isinstance(engine, DefaultContextEngine)
    assert engine.max_context_units == 50


def test_build_context_service() -> None:
    service = build_context_service()

    assert isinstance(service, RepositoryContextService)
    assert isinstance(service.engine, DefaultContextEngine)
    assert service.task_understanding is not None
    assert service.task_validator is not None
    assert service.task_grounding is not None
    assert service.task_repository_grounding is not None


def test_build_context_service_is_independent() -> None:
    first = build_context_service()
    second = build_context_service()

    assert first is not second
    assert first.engine is not second.engine
