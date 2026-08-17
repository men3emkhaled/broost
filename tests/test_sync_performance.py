import ast
import unittest
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "webapp" / "server.py"


class SyncPerformanceTests(unittest.TestCase):
    def test_event_feed_batches_order_serialization(self):
        tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "sync_events"
        )
        called_names = {
            node.func.id for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("admin_orders_to_dict", called_names)
        self.assertNotIn("order_to_dict", called_names)


if __name__ == "__main__":
    unittest.main()
