from dataclasses import dataclass


@dataclass(frozen=True)
class MetricResult:
    expected: int
    actual: int
    matched: int

    @property
    def precision(self) -> float:
        if self.actual == 0:
            return 1.0 if self.expected == 0 else 0.0

        return self.matched / self.actual

    @property
    def recall(self) -> float:
        if self.expected == 0:
            return 1.0

        return self.matched / self.expected

    @property
    def f1(self) -> float:
        precision = self.precision
        recall = self.recall

        if precision + recall == 0:
            return 0.0

        return 2 * precision * recall / (precision + recall)
