import sqlite3
import tempfile
import unittest
from pathlib import Path

import database


LEGACY_SCHEMA = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE,
    name TEXT,
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    sort_order INTEGER
);
CREATE TABLE menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    name TEXT UNIQUE,
    base_price REAL,
    is_available INTEGER DEFAULT 1,
    is_popular INTEGER DEFAULT 0
);
CREATE TABLE drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    is_active INTEGER DEFAULT 1,
    unsettled_cash REAL DEFAULT 0.0
);
CREATE TABLE shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TIMESTAMP,
    closed_at TIMESTAMP,
    expected_cash REAL,
    actual_cash REAL,
    cash_sales REAL DEFAULT 0,
    visa_sales REAL DEFAULT 0,
    wallet_sales REAL DEFAULT 0,
    total_sales REAL DEFAULT 0
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    channel TEXT,
    payment_method TEXT,
    subtotal REAL,
    delivery_fee REAL DEFAULT 0,
    total REAL,
    cash_paid REAL,
    change_due REAL,
    driver_id INTEGER,
    status TEXT,
    shift_id INTEGER,
    created_at TIMESTAMP,
    closed_at TIMESTAMP
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    menu_item_id INTEGER,
    size_name TEXT,
    quantity INTEGER,
    price REAL,
    extras_json TEXT
);
"""


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self._original_db_path = database.DB_PATH
        self._original_backup_dir = database.BACKUP_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        database.DB_PATH = str(root / "current.db")
        database.BACKUP_DIR = str(root / "backups")

        database.init_db()
        conn = database.get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('current_marker', 'before_restore')"
        )
        conn.commit()
        conn.close()

        self.legacy_path = root / "old_broost_backup.db"
        legacy = sqlite3.connect(self.legacy_path)
        legacy.executescript(LEGACY_SCHEMA)
        legacy.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            [
                ("cashier_1_name", "Old Cashier"),
                ("cashier_1_pin", "2468"),
                ("cashier_2_name", "Second Cashier"),
                ("cashier_2_pin", "1357"),
                ("legacy_marker", "from_backup"),
            ],
        )
        legacy.execute("INSERT INTO categories (id, name, sort_order) VALUES (1, 'Legacy', 1)")
        legacy.execute(
            "INSERT INTO menu_items (id, category_id, name, base_price) VALUES (1, 1, 'Legacy Meal', 99)"
        )
        legacy.execute("INSERT INTO drivers (id, name) VALUES (1, 'Legacy Driver')")
        legacy.execute(
            "INSERT INTO shifts (id, opened_at, closed_at, expected_cash, actual_cash) "
            "VALUES (1, '2024-01-01 08:00:00', '2024-01-01 20:00:00', 99, 99)"
        )
        legacy.execute(
            "INSERT INTO orders (id, channel, payment_method, subtotal, total, status, shift_id, created_at) "
            "VALUES (1, 'CASHIER', 'CASH', 99, 99, 'COMPLETED', 1, '2024-01-01 09:00:00')"
        )
        legacy.execute(
            "INSERT INTO order_items (order_id, menu_item_id, quantity, price, extras_json) "
            "VALUES (1, 1, 1, 99, '[]')"
        )
        legacy.commit()
        legacy.close()

    def tearDown(self):
        database.DB_PATH = self._original_db_path
        database.BACKUP_DIR = self._original_backup_dir
        self.temp_dir.cleanup()

    def test_old_backup_is_migrated_and_current_data_is_safely_backed_up(self):
        success, result = database.restore_pos_backup(self.legacy_path)
        self.assertTrue(success, result)

        restored = database.get_connection()
        settings = dict(restored.execute("SELECT key, value FROM settings").fetchall())
        self.assertEqual(settings["cashier_1_name"], "DR OMAR")
        self.assertEqual(settings["cashier_1_pin"], "2468")
        self.assertNotIn("cashier_2_name", settings)
        self.assertNotIn("cashier_2_pin", settings)
        self.assertEqual(settings["legacy_marker"], "from_backup")
        self.assertNotIn("current_marker", settings)

        order_columns = {
            row[1] for row in restored.execute("PRAGMA table_info(orders)").fetchall()
        }
        self.assertIn("remote_id", order_columns)
        self.assertIn("customer_trust_status", order_columns)
        item_name = restored.execute(
            "SELECT item_name FROM order_items WHERE order_id=1"
        ).fetchone()[0]
        self.assertEqual(item_name, "Legacy Meal")
        self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        restored.close()

        safety_path = Path(result["safety_backup"])
        self.assertTrue(safety_path.is_file())
        safety = sqlite3.connect(safety_path)
        marker = safety.execute(
            "SELECT value FROM settings WHERE key='current_marker'"
        ).fetchone()
        safety.close()
        self.assertEqual(marker[0], "before_restore")

    def test_invalid_file_is_rejected_without_changing_current_database(self):
        invalid_path = Path(self.temp_dir.name) / "not_a_database.db"
        invalid_path.write_text("not sqlite", encoding="utf-8")

        success, _ = database.restore_pos_backup(invalid_path)
        self.assertFalse(success)

        conn = database.get_connection()
        marker = conn.execute(
            "SELECT value FROM settings WHERE key='current_marker'"
        ).fetchone()
        conn.close()
        self.assertEqual(marker[0], "before_restore")


if __name__ == "__main__":
    unittest.main()
