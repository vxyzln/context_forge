from dataclasses import FrozenInstanceError

import pytest

from context_forge.config import DEFAULTS, ConfigurationDefaults


def test_configuration_defaults_use_canonical_values() -> None:
    assert DEFAULTS.provider == "ollama"
    assert DEFAULTS.model == "qwen2.5-coder:7b"
    assert DEFAULTS.base_url == "http://localhost:11434"
    assert DEFAULTS.temperature == 0.0
    assert DEFAULTS.max_tokens is None


def test_configuration_defaults_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULTS.model = "another-model"  # type: ignore[misc]


def test_configuration_defaults_can_be_constructed_independently() -> None:
    defaults = ConfigurationDefaults()

    assert defaults == DEFAULTS
