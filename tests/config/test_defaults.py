from dataclasses import FrozenInstanceError

import pytest

from context_forge.config import DEFAULTS, ConfigurationDefaults


def test_configuration_defaults_use_canonical_values() -> None:
    assert DEFAULTS.database_path == ".context_forge.db"
    assert DEFAULTS.max_context_units == 20


def test_configuration_defaults_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULTS.database_path = "other.db"


def test_configuration_defaults_can_be_constructed_independently() -> None:
    defaults = ConfigurationDefaults()

    assert defaults == DEFAULTS
