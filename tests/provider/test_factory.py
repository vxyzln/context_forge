from context_forge.provider import (
    DeterministicProvider,
    OllamaProvider,
    ProviderConfig,
    ProviderFactory,
    ProviderTransportConfig,
)


def test_factory_creates_deterministic_provider() -> None:
    provider = ProviderFactory.create(
        ProviderConfig(
            provider="deterministic",
            model="deterministic",
        )
    )

    assert isinstance(provider, DeterministicProvider)


def test_factory_creates_ollama_provider() -> None:
    provider = ProviderFactory.create(
        ProviderConfig(
            provider="ollama",
            model="qwen3:8b",
        )
    )

    assert isinstance(provider, OllamaProvider)


def test_factory_passes_ollama_configuration() -> None:
    transport = ProviderTransportConfig(timeout=30.0)

    provider = ProviderFactory.create(
        ProviderConfig(
            provider="ollama",
            model="qwen3:8b",
            base_url="http://example.test/",
            transport=transport,
        )
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://example.test"
    assert provider.transport is transport
