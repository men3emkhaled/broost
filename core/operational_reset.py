"""Explicit, one-time fresh starts, preserving menu and connection settings."""

from pathlib import Path
import sqlite3
from datetime import datetime
from contextlib import closing


POS_TABLES = ('order_items', 'orders', 'customers', 'shifts',
              'pending_remote_actions', 'pos_order_sync_queue', 'pos_order_deletions')
WEB_TABLES = ('loyalty_transactions', 'reward_codes', 'customer_issues',
              'order_events', 'order_items', 'orders', 'loyalty_accounts',
              'customer_controls', 'reviews')


def reset_sqlite_operations(path, defaults, *, web=False):
    """A reset ID is packaged only for a user-authorized fresh-start release.

    Back up before deleting. Persist the marker in the same transaction, so a
    restart or reinstall cannot erase invoices created after this fresh start.
    Old restored databases lack the marker and cannot re-upload their history.
    """
    reset_id = defaults.get('operational_reset_id', '')
    path = Path(path)
    if not reset_id or not path.exists():
        return False
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        applied = conn.execute("SELECT value FROM settings WHERE key='operational_reset_id'").fetchone()
        if applied and applied[0] == reset_id:
            return False
        folder = path.parent / 'backups' / 'before_fresh_start'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / (path.stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.db')
        with closing(sqlite3.connect(backup)) as target:
            conn.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Fresh-start backup failed integrity verification')
        conn.execute('BEGIN IMMEDIATE')
        tables = WEB_TABLES if web else POS_TABLES
        for table in tables:
            conn.execute(f'DELETE FROM {table}')
        # Deleting orders may have created sync tombstones through triggers.
        if not web:
            conn.execute('DELETE FROM pos_order_deletions')
            conn.execute('DELETE FROM pos_order_sync_queue')
            conn.execute('UPDATE drivers SET unsettled_cash=0')
        conn.executemany('DELETE FROM sqlite_sequence WHERE name=?', ((name,) for name in tables))
        settings = {'operational_reset_id': reset_id}
        if web:
            settings.update(sync_epoch=reset_id, active_sync_key=defaults['sync_key'])
            conn.execute("DELETE FROM settings WHERE key LIKE 'pos_%'")
        else:
            settings.update(web_sync_key=defaults['sync_key'], web_server_url=defaults['server_url'],
                            web_sync_enabled='1', web_sync_epoch=reset_id, web_last_event_id='0',
                            web_initial_orders_queued='1', web_initial_orders_synced='1',
                            web_menu_version='0', web_menu_fingerprint='')
        conn.executemany('INSERT INTO settings(key,value) VALUES (?,?) '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value', settings.items())
        conn.commit()
        return True
    finally:
        conn.close()
