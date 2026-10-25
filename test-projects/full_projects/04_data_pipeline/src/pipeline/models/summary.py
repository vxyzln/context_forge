from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySummary:
    category: str
    total_amount: float
    record_count: int
    average_amount: float
