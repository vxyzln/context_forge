from inventory.domain.enums import StockStatus
from inventory.domain.product import Product


def evaluate_stock_level(current_stock: int, product: Product) -> StockStatus:
    if current_stock <= 0:
        return StockStatus.OUT_OF_STOCK
    if current_stock <= product.reorder_point:
        return StockStatus.LOW_STOCK
    if current_stock > (product.target_stock * 2):
        return StockStatus.OVERSTOCKED
    return StockStatus.OPTIMAL


def calculate_reorder_quantity(current_stock: int, product: Product) -> int:
    if current_stock >= product.target_stock:
        return 0
    return max(0, product.target_stock - current_stock)
