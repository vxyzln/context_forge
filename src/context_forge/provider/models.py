from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRequest:
    task: str
    context: str


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    provider: str
    metadata: dict[str, str]
