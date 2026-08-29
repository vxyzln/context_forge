from context_forge.provider.base import ContextProvider
from context_forge.provider.models import GenerationRequest, GenerationResponse


class DeterministicProvider(ContextProvider):
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            content=(
                f"Task: {request.task}\n"
                f"Context received: {len(request.context)} characters"
            ),
            provider="deterministic",
            model=request.config.model,
            metadata={
                "mode": "deterministic",
            },
        )
