from dataclasses import dataclass


@dataclass
class Product:
    sku: str
    name: str
    unit_price: float
    supplier_id: str
    category: str = "general"
    reorder_point: int = 10
    target_stock: int = 50
