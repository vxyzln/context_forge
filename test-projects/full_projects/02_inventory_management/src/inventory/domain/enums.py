from enum import Enum


class MovementType(str, Enum):
    RECEIPT = "RECEIPT"
    WITHDRAWAL = "WITHDRAWAL"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"


class StockStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OVERSTOCKED = "OVERSTOCKED"
