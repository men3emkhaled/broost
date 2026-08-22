import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReportPerformanceTests(unittest.TestCase):
    def test_history_search_is_debounced(self):
        tree = ast.parse((ROOT / "dialogs" / "reports.py").read_text(encoding="utf-8"))
        search_method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "search_history"
        )
        attributes = {
            node.func.attr for node in ast.walk(search_method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertIn("start", attributes)
        self.assertNotIn("load_analytics", attributes)

    def test_history_table_does_not_silently_truncate_selected_period(self):
        source = (ROOT / "dialogs" / "reports.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("ORDER BY o.id DESC LIMIT 300"), 0)

    def test_local_reporting_indexes_are_created(self):
        source = (ROOT / "database.py").read_text(encoding="utf-8")
        self.assertIn("idx_orders_status_created", source)
        self.assertIn("idx_orders_shift_created", source)
        self.assertIn("idx_order_items_order", source)


if __name__ == "__main__":
    unittest.main()
