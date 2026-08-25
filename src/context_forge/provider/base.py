from abc import ABC, abstractmethod

from context_forge.provider.models import ProviderRequest, ProviderResponse


class ContextProvider(ABC):
    @abstractmethod
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate a response from a provider-neutral context request."""
        raise NotImplementedError
