from inventory.domain.enums import MovementType
from inventory.domain.movement import StockMovement
from inventory.storage.store import InventoryStore


class InventoryOperationError(Exception):
    pass


class InventoryService:
    def __init__(self, store: InventoryStore) -> None:
        self.store = store
        self._next_movement_id = 1

    def receive_stock(
        self, sku: str, quantity: int, reason: str = "Shipment received"
    ) -> StockMovement:
        if quantity <= 0:
            raise InventoryOperationError("Quantity to receive must be positive")
        product = self.store.get_product(sku)
        if not product:
            raise InventoryOperationError(f"Product '{sku}' not found")

        current = self.store.get_stock(sku)
        self.store.set_stock(sku, current + quantity)

        movement = StockMovement(
            movement_id=f"mov_{self._next_movement_id}",
            sku=sku,
            quantity_change=quantity,
            movement_type=MovementType.RECEIPT,
            reason=reason,
        )
        self._next_movement_id += 1
        self.store.record_movement(movement)
        return movement

    def withdraw_stock(
        self, sku: str, quantity: int, reason: str = "Order fulfilled"
    ) -> StockMovement:
        if quantity <= 0:
            raise InventoryOperationError("Quantity to withdraw must be positive")
        product = self.store.get_product(sku)
        if not product:
            raise InventoryOperationError(f"Product '{sku}' not found")

        current = self.store.get_stock(sku)
        if current < quantity:
            raise InventoryOperationError(
                f"Insufficient stock for SKU '{sku}': requested {quantity}, available {current}"
            )

        self.store.set_stock(sku, current - quantity)

        movement = StockMovement(
            movement_id=f"mov_{self._next_movement_id}",
            sku=sku,
            quantity_change=-quantity,
            movement_type=MovementType.WITHDRAWAL,
            reason=reason,
        )
        self._next_movement_id += 1
        self.store.record_movement(movement)
        return movement
