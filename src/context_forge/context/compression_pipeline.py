from context_forge.context.budget_compression import ContextBudgetCompressor
from context_forge.context.compression import ContextCompressor
from context_forge.context.models import ContextPackage


class ContextCompressionPipeline:
    def __init__(
        self,
        compressor: ContextCompressor,
        budget_compressor: ContextBudgetCompressor,
    ) -> None:
        self.compressor = compressor
        self.budget_compressor = budget_compressor

    def compress(
        self,
        package: ContextPackage,
        max_units: int,
    ) -> ContextPackage:
        compressed = self.compressor.compress(package)

        return self.budget_compressor.compress(
            compressed,
            max_units=max_units,
        )
