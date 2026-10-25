from pipeline.models.record import CleanedRecord, RawRecord
from pipeline.validation.schema import parse_numeric, validate_required_fields

REQUIRED_FIELDS = ["id", "user", "amount", "category"]


class RecordCleaner:
    @staticmethod
    def clean(raw: RawRecord) -> CleanedRecord:
        data = raw.raw_data
        validate_required_fields(data, REQUIRED_FIELDS)
        amount = parse_numeric(data["amount"], "amount")

        return CleanedRecord(
            record_id=str(data["id"]).strip(),
            user_id=str(data["user"]).strip().lower(),
            amount=amount,
            category=str(data["category"]).strip().lower(),
            timestamp=str(data.get("timestamp", "2026-01-01T00:00:00Z")).strip(),
        )
