from collections import defaultdict

from pipeline.models.record import CleanedRecord
from pipeline.models.summary import CategorySummary


class DataAggregator:
    @staticmethod
    def aggregate_by_category(records: list[CleanedRecord]) -> list[CategorySummary]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for r in records:
            grouped[r.category].append(r.amount)

        summaries: list[CategorySummary] = []
        for cat in sorted(grouped.keys()):
            amounts = grouped[cat]
            total = sum(amounts)
            count = len(amounts)
            avg = total / count if count > 0 else 0.0
            summaries.append(
                CategorySummary(
                    category=cat,
                    total_amount=round(total, 2),
                    record_count=count,
                    average_amount=round(avg, 2),
                )
            )
        return summaries
