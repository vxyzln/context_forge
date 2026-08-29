from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    temperature: float = 0.0
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Provider model cannot be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Provider temperature must be between 0.0 and 2.0")

        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("Provider max_tokens must be positive")
