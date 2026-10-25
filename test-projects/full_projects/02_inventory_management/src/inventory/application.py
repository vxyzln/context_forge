from inventory.domain.product import Product
from inventory.domain.supplier import Supplier
from inventory.operations.service import InventoryService
from inventory.reporting.reports import InventoryReporter
from inventory.storage.store import InventoryStore


class InventoryApp:
    def __init__(self) -> None:
        self.store = InventoryStore()
        self.service = InventoryService(self.store)
        self.reporter = InventoryReporter(self.store)

    def bootstrap_sample_data(self) -> None:
        sup = Supplier(
            supplier_id="sup_1", name="Acme Hardware", contact_email="orders@acme.local"
        )
        self.store.save_supplier(sup)

        p1 = Product(
            sku="SKU_WIDGET",
            name="Super Widget",
            unit_price=25.0,
            supplier_id="sup_1",
            reorder_point=15,
            target_stock=60,
        )
        p2 = Product(
            sku="SKU_BOLT",
            name="Steel Bolt Pack",
            unit_price=4.5,
            supplier_id="sup_1",
            reorder_point=50,
            target_stock=200,
        )

        self.store.save_product(p1)
        self.store.save_product(p2)

        self.service.receive_stock("SKU_WIDGET", 40, reason="Initial intake")
        self.service.receive_stock("SKU_BOLT", 30, reason="Initial intake")
