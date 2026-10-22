from abc import ABC, abstractmethod

from context_forge.context.models import ContextPackage


class ContextCompressor(ABC):
    @abstractmethod
    def compress(self, package: ContextPackage) -> ContextPackage:
        raise NotImplementedError
