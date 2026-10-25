import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from pathlib import Path

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.validation.schema import PipelineValidationError


class TestDataPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = PipelineOrchestrator()
        self.sample_csv = Path(__file__).resolve().parent.parent / "data" / "sample.csv"

    def test_pipeline_execution_on_csv(self) -> None:
        report = self.orchestrator.process_file(self.sample_csv)
        self.assertEqual(report["total_records_processed"], 5)
        self.assertEqual(report["categories_count"], 3)
        self.assertEqual(report["grand_total_amount"], 517.40)

        # Check books breakdown
        breakdown = {c["category"]: c for c in report["category_breakdown"]}
        self.assertIn("books", breakdown)
        self.assertEqual(breakdown["books"]["count"], 2)
        self.assertEqual(breakdown["books"]["total"], 57.50)

    def test_missing_required_fields_raises_error(self) -> None:
        from pipeline.models.record import RawRecord

        bad_raw = RawRecord(line_number=1, raw_data={"id": "REC_BAD", "amount": 10})
        with self.assertRaises(PipelineValidationError):
            self.orchestrator.cleaner.clean(bad_raw)


if __name__ == "__main__":
    unittest.main()
