from pathlib import Path

from pipeline.aggregation.aggregator import DataAggregator
from pipeline.readers.loader import DataReader
from pipeline.reporting.formatter import PipelineReporter
from pipeline.transforms.cleaner import RecordCleaner


class PipelineOrchestrator:
    def __init__(self) -> None:
        self.reader = DataReader()
        self.cleaner = RecordCleaner()
        self.aggregator = DataAggregator()
        self.reporter = PipelineReporter()

    def process_file(self, file_path: Path) -> dict[str, object]:
        if file_path.suffix.lower() == ".json":
            raw_records = self.reader.read_json(file_path)
        else:
            raw_records = self.reader.read_csv(file_path)

        cleaned_records = [self.cleaner.clean(r) for r in raw_records]
        summaries = self.aggregator.aggregate_by_category(cleaned_records)
        return self.reporter.generate_report(summaries)
