from pipeline.models.summary import CategorySummary


class PipelineReporter:
    @staticmethod
    def generate_report(summaries: list[CategorySummary]) -> dict[str, object]:
        grand_total = sum(s.total_amount for s in summaries)
        grand_records = sum(s.record_count for s in summaries)

        return {
            "categories_count": len(summaries),
            "grand_total_amount": round(grand_total, 2),
            "total_records_processed": grand_records,
            "category_breakdown": [
                {
                    "category": s.category,
                    "total": s.total_amount,
                    "count": s.record_count,
                    "average": s.average_amount,
                }
                for s in summaries
            ],
        }
