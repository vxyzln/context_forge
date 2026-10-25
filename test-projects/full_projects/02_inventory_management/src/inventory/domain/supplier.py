from dataclasses import dataclass


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    contact_email: str
    lead_time_days: int = 7
