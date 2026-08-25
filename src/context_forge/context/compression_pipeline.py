from context_forge.context.budget_compression import ContextBudgetCompressor
from context_forge.context.compression import ContextCompressor
from context_forge.context.deterministic_compression import (
    DeterministicContextCompressor,
)
from context_forge.context.merge import ContextUnitMerger
from context_forge.context.models import ContextPackage


class ContextCompressionPipeline:
    def __init__(
        self,
        compressor: ContextCompressor | DeterministicContextCompressor,
        merger: ContextUnitMerger,
        budget_compressor: ContextBudgetCompressor,
    ) -> None:
        self.compressor = compressor
        self.merger = merger
        self.budget_compressor = budget_compressor

    def compress(
        self,
        package: ContextPackage,
        max_units: int,
    ) -> ContextPackage:
        compressed = self.compressor.compress(package)

        merged_units = self.merger.merge(
            list(compressed.units),
        )

        merged_package = ContextPackage(
            task=compressed.task,
            units=tuple(merged_units),
        )

        return self.budget_compressor.compress(
            merged_package,
            max_units=max_units,
        )
