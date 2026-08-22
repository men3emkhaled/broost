from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path

import database
from core import config
from core.online_sync import OnlineSyncManager
from core.order_finance import cancel_and_reconcile, reconcile_order_finance
from views.dashboard import MainPOSDashboard


ROOT = Path(__file__).resolve().parents[1]


class CashierExperienceTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp_dir.name) / "cashier-ux.db")
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_offline_action_is_durable_and_flushes_once(self):
        manager = OnlineSyncManager()
        completed = []
        manager.queued_action_completed.connect(
            lambda action, context: completed.append((action, context))
        )
        manager.queue_remote_action(
            "accept", 77, {"status": "PREPARING"}, {"local_order_id": 12}
        )
        self.assertEqual(manager.pending_remote_action_count(), 1)
        calls = []
        manager._request_json = lambda path, method="GET", payload=None: calls.append(
            (path, method, payload)
        ) or {}

        self.assertEqual(manager._flush_pending_remote_actions(), 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(completed[0][0], "accept")
        self.assertEqual(completed[0][1]["local_order_id"], 12)

    def test_bad_request_is_never_queued_as_connectivity_failure(self):
        conflict = urllib.error.HTTPError(
            "https://example.test", 409, "Conflict", {}, None
        )
        offline = urllib.error.URLError(TimeoutError())
        self.assertFalse(OnlineSyncManager.is_queueable_error(conflict))
        self.assertTrue(OnlineSyncManager.is_queueable_error(offline))

    def test_stale_queued_action_is_removed_instead_of_retrying_forever(self):
        manager = OnlineSyncManager()
        failed = []
        manager.queued_action_failed.connect(
            lambda action, context, error: failed.append((action, context, error))
        )
        manager.queue_remote_action(
            "accept", 88, {"status": "PREPARING"}, {"local_order_id": 13}
        )
        manager._request_json = lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.HTTPError("https://example.test", 409, "Conflict", {}, None)
        )
        self.assertEqual(manager._flush_pending_remote_actions(), 0)
        self.assertEqual(manager.pending_remote_action_count(), 0)
        self.assertEqual(failed[0][1]["local_order_id"], 13)

    def test_cashier_cash_cancel_reverses_drawer_and_queues_online_delete(self):
        conn = database.get_connection()
        shift_id = conn.execute(
            "INSERT INTO shifts (cashier_name, opened_at, expected_cash) "
            "VALUES ('DR OMAR', '2026-08-22 09:00:00', 200)"
        ).lastrowid
        order_id = conn.execute(
            "INSERT INTO orders "
            "(channel, payment_method, subtotal, delivery_fee, total, status, shift_id, created_at, source) "
            "VALUES ('CASHIER', 'CASH', 100, 0, 100, 'PENDING', ?, "
            "'2026-08-22 12:00:00', 'POS')",
            (shift_id,),
        ).lastrowid
        conn.commit()
        conn.close()
        config.ACTIVE_SHIFT_ID = shift_id

        self.assertTrue(MainPOSDashboard._delete_order_locally(object(), order_id))
        conn = database.get_connection()
        drawer = conn.execute(
            "SELECT expected_cash FROM shifts WHERE id=?", (shift_id,)
        ).fetchone()[0]
        tombstone = conn.execute(
            "SELECT 1 FROM pos_order_deletions WHERE local_order_id=?", (order_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(float(drawer), 100)
        self.assertIsNotNone(tombstone)

    def test_financial_reconciliation_is_idempotent(self):
        conn = database.get_connection()
        shift_id = conn.execute(
            "INSERT INTO shifts (cashier_name, opened_at, expected_cash) VALUES ('DR OMAR', '2026-08-22 09:00:00', 0)"
        ).lastrowid
        order_id = conn.execute(
            "INSERT INTO orders (channel, payment_method, total, delivery_fee, status, shift_id, source, created_at) "
            "VALUES ('CASHIER', 'CASH', 170, 0, 'PENDING', ?, 'POS', '2026-08-22 10:00:00')",
            (shift_id,),
        ).lastrowid
        reconcile_order_finance(conn, order_id, fallback_shift_id=shift_id)
        reconcile_order_finance(conn, order_id, fallback_shift_id=shift_id)
        self.assertEqual(conn.execute("SELECT expected_cash FROM shifts WHERE id=?", (shift_id,)).fetchone()[0], 170)
        cancel_and_reconcile(conn, order_id, fallback_shift_id=shift_id)
        cancel_and_reconcile(conn, order_id, fallback_shift_id=shift_id)
        self.assertEqual(conn.execute("SELECT expected_cash FROM shifts WHERE id=?", (shift_id,)).fetchone()[0], 0)
        conn.close()

    def test_incremental_sync_only_returns_dirty_orders(self):
        conn = database.get_connection()
        order_id = conn.execute(
            "INSERT INTO orders (channel, payment_method, total, status, source, created_at) "
            "VALUES ('CASHIER', 'CASH', 50, 'PENDING', 'POS', '2026-08-22 10:00:00')"
        ).lastrowid
        conn.commit()
        conn.close()
        manager = OnlineSyncManager()
        self.assertIn(order_id, [row["local_order_id"] for row in manager._orders_for_sync(False)])
        conn = database.get_connection()
        conn.execute("DELETE FROM pos_order_sync_queue WHERE local_order_id=?", (order_id,))
        conn.commit()
        conn.close()
        self.assertNotIn(order_id, [row["local_order_id"] for row in manager._orders_for_sync(False)])

    def test_business_day_boundary_never_moves_to_shift_close(self):
        from unittest.mock import patch
        fixed_now = __import__("datetime").datetime(2026, 8, 22, 12, 0, 0)
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO shifts (cashier_name, opened_at, closed_at) VALUES ('DR OMAR', '2026-08-22 09:00:00', '2026-08-22 10:00:00')"
        )
        conn.commit()
        conn.close()
        with patch("database.datetime") as mocked:
            mocked.now.return_value = fixed_now
            self.assertEqual(database.get_business_day_start().hour, 8)

    def test_ux_guards_are_present_in_dashboard(self):
        source = (ROOT / "views" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("if self._checkout_in_progress:", source)
        self.assertIn("أمامك 8 ثوانٍ للتراجع", source)
        self.assertIn("def open_notification_center", source)
        self.assertIn("● أوفلاين • يعمل محليًا", source)
        self.assertIn("محفوظ محليًا — سيتم التنفيذ تلقائيًا", source)


if __name__ == "__main__":
    unittest.main()
