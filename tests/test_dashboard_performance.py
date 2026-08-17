import ast
import unittest
from pathlib import Path


DASHBOARD_PATH = Path(__file__).resolve().parents[1] / "views" / "dashboard.py"


def method_node(name):
    tree = ast.parse(DASHBOARD_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"method {name!r} was not found")


def called_attributes(node):
    return {
        call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }


class DashboardResponsivenessTests(unittest.TestCase):
    def test_startup_has_no_artificial_sleep(self):
        app_source = (DASHBOARD_PATH.parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("time.sleep(", app_source)

    def test_clock_tick_does_not_rebuild_active_order_cards(self):
        calls = called_attributes(method_node("refresh_pending_orders_timers"))
        self.assertNotIn("load_pending_delivery_orders", calls)
        self.assertIn("_refresh_pending_timer_labels", calls)

    def test_remote_order_actions_never_call_railway_on_gui_thread(self):
        for method_name in (
            "delete_order_action",
            "dispatch_delivery_order",
            "complete_order",
        ):
            with self.subTest(method=method_name):
                calls = called_attributes(method_node(method_name))
                self.assertNotIn("update_remote_order_now", calls)
                self.assertIn("_start_online_order_action", calls)

    def test_printer_detection_and_receipt_output_are_background_jobs(self):
        for method_name in (
            "auto_detect_printer_on_startup",
            "_print_receipts_async",
            "_start_backup_job",
        ):
            with self.subTest(method=method_name):
                calls = called_attributes(method_node(method_name))
                self.assertIn("start", calls)


if __name__ == "__main__":
    unittest.main()
