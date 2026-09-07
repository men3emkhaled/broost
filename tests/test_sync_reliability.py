import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import database
from core.online_sync import OnlineSyncManager
from core.pos_defaults import FALLBACK_SERVER_URL


@contextmanager
def connection():
    conn = database.get_connection()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class SyncReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.original_path = database.DB_PATH
        self.temp = tempfile.TemporaryDirectory()
        database.DB_PATH = str(Path(self.temp.name) / "pos.db")
        database.init_db()
        with connection() as conn:
            self.order_id = conn.execute(
                "INSERT INTO orders (channel, payment_method, total, status, source) "
                "VALUES ('CASHIER', 'CASH', 50, 'PENDING', 'POS')"
            ).lastrowid

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.temp.cleanup()

    def test_existing_installation_migrates_once_and_preserves_orders_and_key(self):
        with connection() as conn:
            conn.executemany("UPDATE settings SET value=? WHERE key=?", [
                ("https://broost-production-4411.up.railway.app/", "web_server_url"),
                ("installation-key", "web_sync_key"),
                ("1", "web_initial_orders_synced"), ("1", "web_initial_orders_queued"),
            ])
        database.init_db()
        with connection() as conn:
            settings = dict(conn.execute("SELECT key,value FROM settings"))
            self.assertEqual(settings["web_server_url"], FALLBACK_SERVER_URL)
            self.assertEqual(settings["web_sync_key"], "installation-key")
            self.assertEqual(settings["web_initial_orders_synced"], "0")
            self.assertEqual(settings["web_initial_orders_queued"], "0")
            self.assertIsNotNone(conn.execute("SELECT id FROM orders WHERE id=?", (self.order_id,)).fetchone())
            conn.execute("UPDATE settings SET value='1' WHERE key='web_initial_orders_synced'")
        database.init_db()
        self.assertEqual(OnlineSyncManager()._setting("web_initial_orders_synced"), "1")

    def test_custom_server_is_preserved(self):
        with connection() as conn:
            conn.execute("UPDATE settings SET value='http://localhost:8765' WHERE key='web_server_url'")
        database.init_db()
        self.assertEqual(OnlineSyncManager()._connection_values()[0], "http://localhost:8765")

    def test_edit_during_upload_remains_queued_until_new_snapshot_is_sent(self):
        manager = OnlineSyncManager()
        sent = []

        def request(path, **kwargs):
            sent.extend(kwargs["payload"]["orders"])
            if len(sent) == 1:
                with connection() as conn:
                    conn.execute("UPDATE orders SET notes='new note' WHERE id=?", (self.order_id,))
            return {"mappings": {}, "deleted_local_order_ids": []}

        manager._request_json = request
        manager._push_pos_orders()
        self.assertTrue(manager.has_pending_pos_orders())
        manager._push_pos_orders()
        self.assertFalse(manager.has_pending_pos_orders())
        self.assertEqual(sent[1]["notes"], "new note")

    def test_instant_push_does_not_overlap_poll_push(self):
        manager = OnlineSyncManager()
        calls = []

        def request(path, **kwargs):
            calls.append(path)
            manager._push_pos_orders()
            return {"mappings": {}, "deleted_local_order_ids": []}

        manager._request_json = request
        manager._push_pos_orders()
        self.assertEqual(len(calls), 1)
        self.assertFalse(manager.has_pending_pos_orders())

    def test_failed_upload_keeps_order_for_retry(self):
        manager = OnlineSyncManager()
        def fail(*args, **kwargs):
            raise TimeoutError("network timeout")
        manager._request_json = fail
        with self.assertRaises(TimeoutError):
            manager._push_pos_orders()
        self.assertTrue(manager.has_pending_pos_orders())
        self.assertFalse(manager._pos_push_lock.locked())

    def test_new_database_has_login_settings_without_overwriting_custom_passwords(self):
        with connection() as conn:
            settings = dict(conn.execute("SELECT key, value FROM settings"))
            self.assertEqual(settings['app_password'], '9999')
            self.assertEqual(settings['delete_password'], '9999')
            conn.execute("UPDATE settings SET value='custom-pin' WHERE key='app_password'")
        database.init_db()
        with connection() as conn:
            self.assertEqual(conn.execute("SELECT value FROM settings WHERE key='app_password'").fetchone()[0], 'custom-pin')

    def test_deleted_order_does_not_leave_a_permanent_upload_queue_entry(self):
        with connection() as conn:
            conn.execute("DELETE FROM orders WHERE id=?", (self.order_id,))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pos_order_sync_queue").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT local_order_id FROM pos_order_deletions").fetchone()[0], self.order_id)

    def test_new_pending_action_survives_older_inflight_action(self):
        manager = OnlineSyncManager()
        manager.queue_remote_action('accept', 77, {'status': 'PREPARING'}, {'local_order_id': 1})
        completed = []
        manager.queued_action_completed.connect(lambda action, context: completed.append(action))
        def request(*args, **kwargs):
            manager.queue_remote_action('reject', 77, {'status': 'CANCELLED'}, {'local_order_id': 1})
            return {}
        manager._request_json = request
        self.assertEqual(manager._flush_pending_remote_actions(), 1)
        self.assertEqual(completed, [])
        with connection() as conn:
            self.assertEqual(conn.execute("SELECT action_type FROM pending_remote_actions").fetchone()[0], 'reject')

    def test_reused_remote_id_does_not_replace_a_different_online_invoice(self):
        manager = OnlineSyncManager()
        first = dict(id=77, public_number='ONLINE-OLD', source='ONLINE', status='COMPLETED',
                     total=0, customer_phone='01077770001', created_at='2026-08-01T10:00:00Z', items=[])
        manager._import_online_order(first)
        old_id = first['local_order_id']
        second = {**first, 'public_number': 'ONLINE-NEW', 'customer_phone': '01077770002'}
        manager._import_online_order(second)
        self.assertNotEqual(second['local_order_id'], old_id)
        with connection() as conn:
            self.assertEqual(conn.execute("SELECT public_number, remote_id FROM orders WHERE id=?", (old_id,)).fetchone(), ('ONLINE-OLD', None))
        orphan = next(o for o in manager._orders_for_sync(False) if o['local_order_id'] == old_id)
        self.assertEqual(orphan['source'], 'ONLINE')

    def test_instant_push_respects_disabled_sync(self):
        from unittest.mock import patch
        manager = OnlineSyncManager()
        with connection() as conn:
            conn.execute("UPDATE settings SET value='0' WHERE key='web_sync_enabled'")
        class InlineThread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
        with patch('core.online_sync.threading.Thread', InlineThread), patch.object(manager, '_push_pos_orders') as push:
            manager.push_pos_orders_now()
            push.assert_not_called()


if __name__ == "__main__":
    unittest.main()
