from dataclasses import dataclass, field
from datetime import UTC, datetime

from inventory.domain.enums import MovementType


@dataclass(frozen=True)
class StockMovement:
    movement_id: str
    sku: str
    quantity_change: int
    movement_type: MovementType
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
