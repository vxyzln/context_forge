from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPriority:
    score: float
    reason: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("Priority score must be between 0.0 and 1.0")
