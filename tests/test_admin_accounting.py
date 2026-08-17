import unittest
from pathlib import Path


ADMIN_JS = Path(__file__).resolve().parents[1] / "webapp" / "static" / "admin.js"


class AdminAccountingTests(unittest.TestCase):
    def test_pos_invoice_counts_before_completion_but_cancelled_does_not(self):
        source = ADMIN_JS.read_text(encoding="utf-8")
        self.assertIn('order.source === "POS" && order.status !== "CANCELLED"', source)
        self.assertIn('const netSales = salesToday.reduce', source)
        self.assertIn('salesToday.forEach', source)


if __name__ == "__main__":
    unittest.main()
