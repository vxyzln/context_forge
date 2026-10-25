from inventory.policies.reorder import calculate_reorder_quantity, evaluate_stock_level
from inventory.storage.store import InventoryStore


class InventoryReporter:
    def __init__(self, store: InventoryStore) -> None:
        self.store = store

    def generate_stock_summary(self) -> dict[str, object]:
        products = self.store.list_products()
        items: list[dict[str, object]] = []

        total_valuation = 0.0
        reorder_needed = 0

        for p in products:
            qty = self.store.get_stock(p.sku)
            status = evaluate_stock_level(qty, p)
            reorder_qty = calculate_reorder_quantity(qty, p)
            val = qty * p.unit_price
            total_valuation += val
            if reorder_qty > 0:
                reorder_needed += 1

            items.append(
                {
                    "sku": p.sku,
                    "name": p.name,
                    "current_stock": qty,
                    "unit_price": p.unit_price,
                    "valuation": round(val, 2),
                    "status": status.value,
                    "reorder_quantity": reorder_qty,
                }
            )

        return {
            "total_skus": len(products),
            "total_valuation": round(total_valuation, 2),
            "reorder_needed_count": reorder_needed,
            "items": items,
        }
