import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest

from inventory.application import InventoryApp
from inventory.operations.service import InventoryOperationError


class TestInventoryManagement(unittest.TestCase):
    def setUp(self) -> None:
        self.app = InventoryApp()
        self.app.bootstrap_sample_data()

    def test_bootstrap_stock_levels(self) -> None:
        self.assertEqual(self.app.store.get_stock("SKU_WIDGET"), 40)
        self.assertEqual(self.app.store.get_stock("SKU_BOLT"), 30)

    def test_stock_receipt_increases_quantity(self) -> None:
        mov = self.app.service.receive_stock("SKU_WIDGET", 10)
        self.assertEqual(mov.quantity_change, 10)
        self.assertEqual(self.app.store.get_stock("SKU_WIDGET"), 50)

    def test_stock_withdrawal_decreases_quantity(self) -> None:
        mov = self.app.service.withdraw_stock("SKU_WIDGET", 15)
        self.assertEqual(mov.quantity_change, -15)
        self.assertEqual(self.app.store.get_stock("SKU_WIDGET"), 25)

    def test_overdraw_stock_raises_error(self) -> None:
        with self.assertRaises(InventoryOperationError):
            self.app.service.withdraw_stock("SKU_WIDGET", 100)

    def test_reorder_reporting(self) -> None:
        # Stock levels: WIDGET has 40 (target 60), BOLT has 30 (target 200)
        summary = self.app.reporter.generate_stock_summary()
        self.assertEqual(summary["total_skus"], 2)
        self.assertEqual(summary["reorder_needed_count"], 2)


if __name__ == "__main__":
    unittest.main()
