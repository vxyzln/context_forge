from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionConfig:
    """Configuration shared by deterministic context compressors."""

    max_units: int | None = None
    max_facts_per_unit: int | None = None
    max_signals_per_unit: int | None = None
    max_inferences_per_unit: int | None = None
    max_evidence_per_item: int | None = None

    def __post_init__(self) -> None:
        limits = (
            self.max_units,
            self.max_facts_per_unit,
            self.max_signals_per_unit,
            self.max_inferences_per_unit,
            self.max_evidence_per_item,
        )

        for limit in limits:
            if limit is not None and limit < 0:
                raise ValueError("Compression limits must be non-negative")
