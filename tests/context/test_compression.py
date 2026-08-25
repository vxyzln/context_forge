import pytest

from context_forge.context import CompressionConfig, ContextCompressor
from context_forge.context.models import ContextPackage


class TestContextCompressor(ContextCompressor):
    def compress(self, package: ContextPackage) -> ContextPackage:
        return package


def test_context_compressor_is_abstract() -> None:
    assert issubclass(ContextCompressor, object)

    with pytest.raises(TypeError):
        ContextCompressor()


def test_context_compressor_accepts_context_package() -> None:
    package = ContextPackage(task="authentication")

    compressed = TestContextCompressor().compress(package)

    assert compressed == package


def test_compression_config_defaults_to_unbounded() -> None:
    config = CompressionConfig()

    assert config.max_units is None
    assert config.max_facts_per_unit is None
    assert config.max_signals_per_unit is None
    assert config.max_inferences_per_unit is None
    assert config.max_evidence_per_item is None


@pytest.mark.parametrize(
    "field",
    (
        "max_units",
        "max_facts_per_unit",
        "max_signals_per_unit",
        "max_inferences_per_unit",
        "max_evidence_per_item",
    ),
)
def test_compression_config_rejects_negative_limits(field: str) -> None:
    with pytest.raises(
        ValueError,
        match="Compression limits must be non-negative",
    ):
        CompressionConfig(**{field: -1})


def test_compression_config_accepts_zero_limits() -> None:
    config = CompressionConfig(
        max_units=0,
        max_facts_per_unit=0,
        max_signals_per_unit=0,
        max_inferences_per_unit=0,
        max_evidence_per_item=0,
    )

    assert config.max_units == 0
    assert config.max_facts_per_unit == 0
    assert config.max_signals_per_unit == 0
    assert config.max_inferences_per_unit == 0
    assert config.max_evidence_per_item == 0


def test_compression_config_preserves_explicit_limits() -> None:
    config = CompressionConfig(
        max_units=10,
        max_facts_per_unit=5,
        max_signals_per_unit=4,
        max_inferences_per_unit=3,
        max_evidence_per_item=2,
    )

    assert config.max_units == 10
    assert config.max_facts_per_unit == 5
    assert config.max_signals_per_unit == 4
    assert config.max_inferences_per_unit == 3
    assert config.max_evidence_per_item == 2
