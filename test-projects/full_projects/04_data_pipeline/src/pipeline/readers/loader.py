import csv
import json
from pathlib import Path

from pipeline.models.record import RawRecord


class DataReader:
    @staticmethod
    def read_csv(file_path: Path) -> list[RawRecord]:
        records: list[RawRecord] = []
        with file_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                records.append(RawRecord(line_number=idx, raw_data=dict(row)))
        return records

    @staticmethod
    def read_json(file_path: Path) -> list[RawRecord]:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [
            RawRecord(line_number=idx, raw_data=item)
            for idx, item in enumerate(data, start=1)
        ]
