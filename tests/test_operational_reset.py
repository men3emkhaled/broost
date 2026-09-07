import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager

import database
from core.operational_reset import reset_sqlite_operations, POS_TABLES, WEB_TABLES
from webapp import server
from fastapi import HTTPException


@contextmanager
def connection(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class OperationalResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'pos.db'
        self.defaults = {'server_url': 'http://127.0.0.1:1', 'sync_key': 'new-test-key',
                         'operational_reset_id': 'authorized-reset-1'}
        with patch.object(database, 'DB_PATH', str(self.path)), patch.object(database, 'load_pos_defaults', return_value={**self.defaults, 'operational_reset_id': ''}):
            database.init_db()
        with connection(self.path) as conn:
            conn.execute("INSERT INTO customers(name,phone) VALUES ('Old customer','01000000000')")
            conn.execute("INSERT INTO shifts(cashier_name,expected_cash) VALUES ('Cashier',100)")
            conn.execute("INSERT INTO orders(id,source,status,total) VALUES (3879,'POS','COMPLETED',405)")
            conn.execute('UPDATE drivers SET unsettled_cash=100')

    def tearDown(self):
        self.temp.cleanup()

    def test_reset_preserves_menu_backs_up_and_starts_at_one(self):
        with connection(self.path) as conn:
            menu = conn.execute('SELECT * FROM menu_items').fetchall()
        self.assertTrue(reset_sqlite_operations(self.path, self.defaults))
        with connection(self.path) as conn:
            for table in POS_TABLES:
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0, table)
            self.assertEqual(conn.execute('SELECT * FROM menu_items').fetchall(), menu)
            self.assertEqual(conn.execute('SELECT SUM(unsettled_cash) FROM drivers').fetchone()[0], 0)
            self.assertEqual(dict(conn.execute('SELECT key,value FROM settings'))['web_sync_key'], 'new-test-key')
            self.assertEqual(conn.execute("INSERT INTO orders(source,total) VALUES ('POS',25)").lastrowid, 1)
        self.assertFalse(reset_sqlite_operations(self.path, self.defaults))
        with connection(self.path) as conn:
            self.assertEqual(conn.execute('SELECT total FROM orders').fetchone()[0], 25)
        backups = list((self.path.parent / 'backups/before_fresh_start').glob('*.db'))
        self.assertEqual(len(backups), 1)
        with connection(backups[0]) as conn:
            self.assertEqual(conn.execute('SELECT id,total FROM orders').fetchone(), (3879,405))

    def test_backup_failure_leaves_history_untouched(self):
        with patch('core.operational_reset.Path.mkdir', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                reset_sqlite_operations(self.path, self.defaults)
        with connection(self.path) as conn:
            self.assertEqual(conn.execute('SELECT id FROM orders').fetchone()[0], 3879)

    def test_no_reset_without_explicit_release_marker(self):
        self.assertFalse(reset_sqlite_operations(self.path, {**self.defaults, 'operational_reset_id': ''}))
        with connection(self.path) as conn:
            self.assertEqual(conn.execute('SELECT id FROM orders').fetchone()[0], 3879)

    def test_old_sync_credential_is_rejected_after_rotation(self):
        with patch.object(server, 'db_connection') as connection, patch.object(server, 'setting', side_effect=lambda c,k,d='': {'active_sync_key':'new-test-key','sync_key':'old-test-key'}.get(k,d)):
            connection.return_value.__enter__.return_value = object()
            with self.assertRaises(HTTPException) as failure:
                server.require_sync('old-test-key')
            self.assertEqual(failure.exception.status_code, 401)
            server.require_sync('new-test-key')

    def test_local_web_reset_clears_events_and_loyalty_preserving_menu(self):
        folder = Path(self.temp.name) / 'web'
        web_path = folder / 'broost_web.db'
        with patch.object(server, 'DATA_DIR', folder), patch.object(server, 'DB_PATH', web_path), patch.object(server, 'PROOFS_DIR', folder/'proofs'), patch.object(server, 'USING_POSTGRES', False):
            server.init_web_db()
        with connection(web_path) as conn:
            values = {'public_number':'POS-80','resume_token':'token','source':'POS','total':100,
                      'fulfillment':'PICKUP','customer_name':'Old','customer_phone':'',
                      'payment_method':'CASH','payment_status':'CONFIRMED','status':'COMPLETED',
                      'subtotal':100,'created_at':'2026-01-01','updated_at':'2026-01-01'}
            fields = ','.join(values)
            placeholders = ','.join('?' for _ in values)
            conn.execute(f'INSERT INTO orders(id,{fields}) VALUES (80,{placeholders})',tuple(values.values()))
            conn.execute("INSERT INTO order_events(order_id,event_type,created_at) VALUES (80,'ORDER_CREATED','2026-01-01')")
        self.assertTrue(reset_sqlite_operations(web_path, self.defaults, web=True))
        with connection(web_path) as conn:
            for table in WEB_TABLES:
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0, table)
            self.assertEqual(conn.execute(f'INSERT INTO orders({fields}) VALUES ({placeholders})',tuple(values.values())).lastrowid, 1)
            self.assertEqual(dict(conn.execute('SELECT key,value FROM settings'))['active_sync_key'],'new-test-key')


if __name__ == '__main__':
    unittest.main()
