import pytest

from context_forge.provider import ProviderConfig


def test_provider_config_uses_defaults() -> None:
    config = ProviderConfig(model="qwen3:8b")

    assert config.model == "qwen3:8b"
    assert config.temperature == 0.0
    assert config.max_tokens is None


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


def test_provider_config_preserves_explicit_values() -> None:
    config = ProviderConfig(
        model="qwen3:8b",
        temperature=0.7,
        max_tokens=2048,
    )

    assert config.model == "qwen3:8b"
    assert config.temperature == 0.7
    assert config.max_tokens == 2048


def test_provider_config_is_generation_only() -> None:
    config = ProviderConfig(
        model="qwen3:8b",
        temperature=0.7,
        max_tokens=2048,
    )

    assert config.model == "qwen3:8b"
    assert config.temperature == 0.7
    assert config.max_tokens == 2048
