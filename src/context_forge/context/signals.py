from dataclasses import dataclass


@dataclass(frozen=True)
class RelevanceSignals:
    lexical: float = 0.0
    structural: float = 0.0
    symbol: float = 0.0
    dependency: float = 0.0

    def total(self) -> float:
        return self.lexical + self.structural + self.symbol + self.dependency
