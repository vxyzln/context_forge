from dataclasses import dataclass, field

from context_forge.provider.config import ProviderConfig


@dataclass(frozen=True)
class GenerationRequest:
    task: str
    context: str
    config: ProviderConfig


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class GenerationResponse:
    content: str
    provider: str
    model: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    reasoning: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
