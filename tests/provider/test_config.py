import pytest

from context_forge.provider import ProviderConfig


def test_provider_config_uses_defaults() -> None:
    config = ProviderConfig(model="qwen3:8b")

    assert config.provider == "ollama"
    assert config.model == "qwen3:8b"
    assert config.temperature == 0.0
    assert config.max_tokens is None
    assert config.base_url == "http://localhost:11434"
    assert config.transport.timeout == 60.0


@pytest.mark.parametrize(
    "provider",
    ("", "   "),
)
def test_provider_config_rejects_empty_provider(provider: str) -> None:
    with pytest.raises(ValueError, match="Provider name cannot be empty"):
        ProviderConfig(
            provider=provider,
            model="qwen3:8b",
        )


def test_provider_config_rejects_unsupported_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        ProviderConfig(
            provider="unknown",
            model="qwen3:8b",
        )


@pytest.mark.parametrize(
    "kwargs",
    (
        {"model": ""},
        {"model": "   "},
    ),
)
def test_provider_config_rejects_empty_model(
    kwargs: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="model cannot be empty"):
        ProviderConfig(**kwargs)


@pytest.mark.parametrize("temperature", (-0.1, 2.1))
def test_provider_config_rejects_invalid_temperature(
    temperature: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="temperature must be between 0.0 and 2.0",
    ):
        ProviderConfig(
            model="qwen3:8b",
            temperature=temperature,
        )


def test_provider_config_rejects_invalid_max_tokens() -> None:
    with pytest.raises(ValueError, match="max_tokens must be positive"):
        ProviderConfig(
            model="qwen3:8b",
            max_tokens=0,
        )


def test_provider_config_rejects_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base URL cannot be empty"):
        ProviderConfig(
            model="qwen3:8b",
            base_url="   ",
        )


def test_provider_config_normalizes_provider_and_base_url() -> None:
    config = ProviderConfig(
        provider=" OLLAMA ",
        model="qwen3:8b",
        base_url="http://localhost:11434/",
    )

    assert config.provider == "ollama"
    assert config.base_url == "http://localhost:11434"


def test_provider_config_accepts_deterministic_provider() -> None:
    config = ProviderConfig(
        provider="deterministic",
        model="deterministic",
    )

    assert config.provider == "deterministic"


def test_provider_config_preserves_explicit_values() -> None:
    config = ProviderConfig(
        provider="ollama",
        model="qwen3:8b",
        temperature=0.7,
        max_tokens=2048,
        base_url="http://example.test",
    )

    assert config.provider == "ollama"
    assert config.model == "qwen3:8b"
    assert config.temperature == 0.7
    assert config.max_tokens == 2048
    assert config.base_url == "http://example.test"


def test_provider_config_is_generation_only() -> None:
    config = ProviderConfig(
        model="qwen3:8b",
        temperature=0.7,
        max_tokens=2048,
    )

    assert config.model == "qwen3:8b"
    assert config.temperature == 0.7
    assert config.max_tokens == 2048
