from inventory.domain.movement import StockMovement
from inventory.domain.product import Product
from inventory.domain.supplier import Supplier


class InventoryStore:
    def __init__(self) -> None:
        self._products: dict[str, Product] = {}
        self._suppliers: dict[str, Supplier] = {}
        self._stock_levels: dict[str, int] = {}
        self._movements: list[StockMovement] = []

    def save_product(self, product: Product) -> None:
        self._products[product.sku] = product
        if product.sku not in self._stock_levels:
            self._stock_levels[product.sku] = 0

    def get_product(self, sku: str) -> Product | None:
        return self._products.get(sku)

    def list_products(self) -> list[Product]:
        return list(self._products.values())

    def save_supplier(self, supplier: Supplier) -> None:
        self._suppliers[supplier.supplier_id] = supplier

    def get_supplier(self, supplier_id: str) -> Supplier | None:
        return self._suppliers.get(supplier_id)

    def get_stock(self, sku: str) -> int:
        return self._stock_levels.get(sku, 0)

    def set_stock(self, sku: str, quantity: int) -> None:
        self._stock_levels[sku] = quantity

    def record_movement(self, movement: StockMovement) -> None:
        self._movements.append(movement)

    def list_movements_by_sku(self, sku: str) -> list[StockMovement]:
        return [m for m in self._movements if m.sku == sku]
