from dataclasses import dataclass, field

from context_forge.provider.transport import ProviderTransportConfig


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "ollama"
    model: str = "qwen2.5-coder:7b"
    temperature: float = 0.0
    max_tokens: int | None = None
    base_url: str = "http://localhost:11434"
    transport: ProviderTransportConfig = field(
        default_factory=ProviderTransportConfig,
    )

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()

        if not provider:
            raise ValueError("Provider name cannot be empty")

        if provider not in {"ollama", "deterministic"}:
            raise ValueError(f"Unsupported provider: {self.provider}")

        if not self.model.strip():
            raise ValueError("Provider model cannot be empty")

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Provider temperature must be between 0.0 and 2.0")

        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("Provider max_tokens must be positive")

        if not self.base_url.strip():
            raise ValueError("Provider base URL cannot be empty")

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
