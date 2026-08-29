from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderTransportConfig:
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("Provider timeout must be positive")
