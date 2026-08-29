from abc import ABC, abstractmethod

from context_forge.provider.models import GenerationRequest, GenerationResponse


class ContextProvider(ABC):
    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError
