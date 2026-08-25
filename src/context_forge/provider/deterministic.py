from context_forge.provider.base import ContextProvider
from context_forge.provider.models import ProviderRequest, ProviderResponse


class DeterministicProvider(ContextProvider):
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            content=(
                f"Task: {request.task}\n"
                f"Context received: {len(request.context)} characters"
            ),
            provider="deterministic",
            metadata={
                "mode": "deterministic",
            },
        )
