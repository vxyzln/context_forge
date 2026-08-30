from context_forge.provider.base import ContextProvider
from context_forge.provider.config import ProviderConfig
from context_forge.provider.deterministic import DeterministicProvider
from context_forge.provider.ollama import OllamaProvider


class ProviderFactory:
    @staticmethod
    def create(config: ProviderConfig) -> ContextProvider:
        if config.provider == "ollama":
            return OllamaProvider(
                base_url=config.base_url,
                transport=config.transport,
            )
        if config.provider == "deterministic":
            return DeterministicProvider()

        raise ValueError(f"Unsupported provider: {config.provider}")
