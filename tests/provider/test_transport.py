import pytest

from context_forge.provider import ProviderTransportConfig


def test_transport_config_defaults() -> None:
    config = ProviderTransportConfig()

    assert config.timeout == 60.0


def test_transport_config_preserves_timeout() -> None:
    config = ProviderTransportConfig(timeout=30.0)

    assert config.timeout == 30.0


def test_transport_config_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout must be positive"):
        ProviderTransportConfig(timeout=0)
