import tempfile
import unittest
from pathlib import Path

import database


class DatabaseResponsivenessTests(unittest.TestCase):
    def test_local_database_uses_wal_and_bounded_lock_waits(self):
        original_path = database.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as folder:
                database.DB_PATH = str(Path(folder) / "performance.db")
                database.init_db()
                connection = database.get_connection()
                try:
                    self.assertEqual(
                        str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower(),
                        "wal",
                    )
                    self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
                finally:
                    connection.close()
        finally:
            database.DB_PATH = original_path

    def test_deleted_pos_orders_do_not_create_remote_sync_artifacts(self):
        original_path = database.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as folder:
                database.DB_PATH = str(Path(folder) / "deletion-sync.db")
                database.init_db()
                connection = database.get_connection()
                try:
                    cursor = connection.execute(
                        "INSERT INTO orders "
                        "(channel, payment_method, subtotal, total, status, created_at, source) "
                        "VALUES ('CASHIER', 'CASH', 125, 125, 'PENDING', "
                        "'2026-08-17 12:00:00', 'POS')"
                    )
                    order_id = int(cursor.lastrowid)
                    connection.execute("DELETE FROM orders WHERE id=?", (order_id,))
                    connection.commit()
                    self.assertIsNone(connection.execute(
                        "SELECT id FROM orders WHERE id=?", (order_id,)
                    ).fetchone())
                    retired_tables = {row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )}
                    self.assertFalse(retired_tables & {
                        "pos_order_deletions", "pos_order_sync_queue",
                        "pending_remote_actions",
                    })
                finally:
                    connection.close()
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
