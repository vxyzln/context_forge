from abc import ABC, abstractmethod

from context_forge.context.models import ContextPackage


class ContextCompressor(ABC):
    """Compress a context package without changing its semantic contract."""

    @abstractmethod
    def compress(self, package: ContextPackage) -> ContextPackage:
        """Return a compressed context package."""
        raise NotImplementedError
