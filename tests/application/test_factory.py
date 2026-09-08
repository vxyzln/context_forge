from context_forge.application import (
    ContextGenerationService,
    build_context_engine,
    build_generation_service,
)
from context_forge.context import (
    ContextSelectionService,
    DefaultContextEngine,
)
from context_forge.provider import (
    DeterministicProvider,
    OllamaProvider,
    ProviderConfig,
)


def test_build_context_engine() -> None:
    engine = build_context_engine()

    assert isinstance(engine, DefaultContextEngine)


def test_build_generation_service() -> None:
    service = build_generation_service(
        ProviderConfig(
            provider="deterministic",
            model="deterministic",
        )
    )

    assert isinstance(service, ContextGenerationService)
    assert isinstance(service.provider, DeterministicProvider)
    assert service.task_understanding is not None
    assert service.task_validator is not None


def test_build_generation_service_is_independent() -> None:
    config = ProviderConfig(
        provider="deterministic",
        model="deterministic",
    )

    first = build_generation_service(config)
    second = build_generation_service(config)

    assert first is not second
    assert first.engine is not second.engine
    assert first.provider is not second.provider


def test_build_generation_service_uses_configured_provider() -> None:
    config = ProviderConfig(
        provider="ollama",
        model="qwen2.5-coder:7b",
    )

    service = build_generation_service(config)

    assert isinstance(service.provider, OllamaProvider)


def test_build_context_engine_accepts_selection_service() -> None:
    selection_service = ContextSelectionService(
        provider=DeterministicProvider(),
        config=ProviderConfig(
            provider="deterministic",
            model="deterministic-selection",
        ),
    )

    engine = build_context_engine(
        selection_service=selection_service,
    )

    assert isinstance(engine, DefaultContextEngine)
    assert engine.selection_service is selection_service


def test_build_generation_service_wires_selection_service() -> None:
    config = ProviderConfig(
        provider="deterministic",
        model="deterministic",
    )

    service = build_generation_service(config)

    assert isinstance(service.engine, DefaultContextEngine)
    assert isinstance(service.engine.selection_service, ContextSelectionService)
