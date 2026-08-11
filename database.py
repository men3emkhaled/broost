import sqlite3
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from core.time_utils import legacy_utc_to_local_db_timestamp

if getattr(sys, 'frozen', False):
    # Bundled executable path
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Standard source script path
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "broost_pos.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Settings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # 2. Customers Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE,
            name TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 3. Categories Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            sort_order INTEGER
        )
    """)
    
    # 4. Menu Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT UNIQUE,
            base_price REAL,
            is_available INTEGER DEFAULT 1,
            is_popular INTEGER DEFAULT 0,
            is_daily_offer INTEGER DEFAULT 0,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
    """)
    
    # 5. Menu Item Sizes Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_item_sizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            name TEXT,
            price_offset REAL,
            FOREIGN KEY(item_id) REFERENCES menu_items(id)
        )
    """)
    
    # 6. Menu Item Extras Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_item_extras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            name TEXT,
            price REAL,
            FOREIGN KEY(item_id) REFERENCES menu_items(id)
        )
    """)

    # Real offers are independent menu entries made from one or more products.
    # Keeping the components in a separate table supports a discounted single
    # item, repeated quantities, and mixed bundles with the same data model.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_id TEXT UNIQUE,
            name TEXT NOT NULL,
            offer_price REAL NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offer_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_id TEXT UNIQUE,
            offer_id INTEGER NOT NULL,
            menu_item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(offer_id) REFERENCES offers(id) ON DELETE CASCADE,
            FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
        )
    """)
    
    # 7. Drivers Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            unsettled_cash REAL DEFAULT 0.0
        )
    """)
    
    # 8. Shifts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashier_name TEXT DEFAULT '',
            opened_at TIMESTAMP,
            closed_at TIMESTAMP,
            expected_cash REAL,
            actual_cash REAL,
            cash_sales REAL DEFAULT 0,
            visa_sales REAL DEFAULT 0,
            wallet_sales REAL DEFAULT 0,
            total_sales REAL DEFAULT 0
        )
    """)
    
    # 9. Orders Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            channel TEXT, -- 'CASHIER' (Eat In) or 'DELIVERY'
            payment_method TEXT, -- 'CASH', 'VISA', 'WALLET'
            subtotal REAL,
            delivery_fee REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            total REAL,
            cash_paid REAL,
            change_due REAL,
            driver_id INTEGER,
            status TEXT, -- 'PENDING', 'DISPATCHED', 'COMPLETED', 'CANCELLED'
            shift_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP,
            closed_at TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(driver_id) REFERENCES drivers(id),
            FOREIGN KEY(shift_id) REFERENCES shifts(id)
        )
    """)
    
    # Migration: add discount column to existing databases if missing
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN notes TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE shifts ADD COLUMN cashier_name TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE drivers ADD COLUMN unsettled_cash REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # 10. Order Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            menu_item_id INTEGER,
            item_name TEXT,
            size_name TEXT,
            quantity INTEGER,
            price REAL,
            extras_json TEXT, -- JSON array of extra names and prices
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
        )
    """)

    # Keep a permanent copy of the sold item name on every invoice.  This
    # preserves historical receipts and reports even if the menu item is
    # deleted or renamed later.
    try:
        cursor.execute("ALTER TABLE order_items ADD COLUMN item_name TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    cursor.execute("""
        UPDATE order_items
        SET item_name = (
            SELECT name FROM menu_items WHERE menu_items.id = order_items.menu_item_id
        )
        WHERE item_name IS NULL OR item_name = ''
    """)

    # Stable identifiers and online-order metadata used by the website sync.
    # Existing numeric IDs remain untouched.
    sync_columns = {
        "categories": [("sync_id", "TEXT")],
        "menu_items": [("sync_id", "TEXT"), ("is_daily_offer", "INTEGER DEFAULT 0")],
        "menu_item_sizes": [("sync_id", "TEXT")],
        "menu_item_extras": [("sync_id", "TEXT")],
        "orders": [
            ("source", "TEXT DEFAULT 'POS'"),
            ("remote_id", "INTEGER"),
            ("public_number", "TEXT"),
            ("online_status", "TEXT"),
            ("payment_status", "TEXT"),
            ("area_name", "TEXT"),
            ("proof_available", "INTEGER DEFAULT 0"),
            ("customer_trust_status", "TEXT"),
            ("customer_completed_orders", "INTEGER DEFAULT 0"),
            ("customer_issue_count", "INTEGER DEFAULT 0"),
            ("customer_confirmed_wallets", "INTEGER DEFAULT 0"),
        ],
    }
    for table_name, columns in sync_columns.items():
        for column_name, column_type in columns:
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            except sqlite3.OperationalError:
                pass

    cursor.execute("UPDATE categories SET sync_id='category-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE menu_items SET sync_id='item-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE menu_item_sizes SET sync_id='size-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE menu_item_extras SET sync_id='extra-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE offers SET sync_id='offer-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE offer_items SET sync_id='offer-item-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE orders SET source='POS' WHERE source IS NULL OR source=''")
    cursor.execute(
        "UPDATE orders SET online_status='PREPARING' "
        "WHERE source='ONLINE' AND online_status='ACCEPTED'"
    )
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_sync_id ON categories(sync_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_menu_items_sync_id ON menu_items(sync_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_menu_sizes_sync_id ON menu_item_sizes(sync_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_menu_extras_sync_id ON menu_item_extras(sync_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_offers_sync_id ON offers(sync_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_offer_items_sync_id ON offer_items(sync_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_offer_items_offer ON offer_items(offer_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_remote_id ON orders(remote_id) WHERE remote_id IS NOT NULL")
    
    conn.commit()
    
    # Seed default configurations & passwords
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("app_password", "9999"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("delete_password", "9999"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("printer_online", "1"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("delivery_fee", "15"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("cashier_1_name", "DR OMAR"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("cashier_1_pin", "1111"))
        conn.commit()

    # Migrate: ensure cashier settings and printer settings exist in older DBs
    for key, val in [("cashier_1_name", "DR OMAR"), ("cashier_1_pin", "1111"),
                     ("printer_paper_width", "80"), ("printer_font_size", "normal"),
                     ("selected_printer", ""),
                     ("master_password", "9999"),
                     ("web_sync_enabled", "1"),
                     ("web_server_url", "http://127.0.0.1:8765"),
                     ("web_sync_key", "broost-local-sync"),
                     ("web_last_event_id", "0"),
                     ("web_menu_version", "0"),
                     ("web_menu_fingerprint", ""),
                     ("web_initial_orders_synced", "0")]:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
    
    # Auto-update old defaults to 9999 if they haven't been customized yet
    cursor.execute("UPDATE settings SET value='9999' WHERE key='app_password' AND value='123'")
    cursor.execute("UPDATE settings SET value='9999' WHERE key='delete_password' AND value='456'")

    # This installation intentionally has one shift/cashier only.  Keep an old
    # backup's historical shifts untouched, but force every future login to the
    # single configured shift and remove obsolete second-cashier settings.
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('cashier_1_name', 'DR OMAR')"
    )
    cursor.execute("DELETE FROM settings WHERE key IN ('cashier_2_name', 'cashier_2_pin')")
    conn.commit()
        
    repair_legacy_online_timestamps(conn)
    cleanup_legacy_mock_data(conn)
    seed_reference_data(conn)
    conn.close()

def repair_legacy_online_timestamps(conn):
    """One-time repair for website UTC values that older sync code saved as local time."""
    cursor = conn.cursor()
    if cursor.execute(
        "SELECT 1 FROM settings WHERE key='online_timestamp_timezone_fixed_v1'"
    ).fetchone():
        return

    rows = cursor.execute(
        "SELECT id, created_at, closed_at FROM orders WHERE source='ONLINE'"
    ).fetchall()
    if rows:
        conn.commit()
        backup_ok, backup_result = run_backup(prefix="pre_online_time_fix")
        if not backup_ok:
            print(f"[Database] Online timestamp repair skipped because backup failed: {backup_result}")
            return
        for order_id, created_at, closed_at in rows:
            cursor.execute(
                "UPDATE orders SET created_at=?, closed_at=? WHERE id=?",
                (
                    legacy_utc_to_local_db_timestamp(created_at),
                    legacy_utc_to_local_db_timestamp(closed_at),
                    order_id,
                ),
            )

    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) "
        "VALUES ('online_timestamp_timezone_fixed_v1', '1')"
    )
    conn.commit()


def cleanup_legacy_mock_data(conn):
    """Remove only the old, unmistakable batches created by the demo generator."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM settings WHERE key='legacy_mock_data_removed_v1'"
    )
    if cursor.fetchone():
        return

    cursor.execute("""
        SELECT id
        FROM shifts
        WHERE COALESCE(cashier_name, '') = ''
          AND opened_at LIKE '____-__-__ 12:00:00.%'
          AND closed_at LIKE '____-__-__ 23:59:00.%'
    """)
    mock_shift_ids = [row[0] for row in cursor.fetchall()]

    if mock_shift_ids:
        # Make a recoverable copy before removing legacy generated records.
        conn.commit()
        success, backup_path = run_backup(prefix="pre_mock_cleanup")
        if not success:
            print(f"[Database] Mock cleanup skipped because backup failed: {backup_path}")
            return

        placeholders = ",".join("?" for _ in mock_shift_ids)
        cursor.execute(
            f"DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE shift_id IN ({placeholders}))",
            mock_shift_ids,
        )
        cursor.execute(
            f"DELETE FROM orders WHERE shift_id IN ({placeholders})",
            mock_shift_ids,
        )
        cursor.execute(
            f"DELETE FROM shifts WHERE id IN ({placeholders})",
            mock_shift_ids,
        )
        print(f"[Database] Removed {len(mock_shift_ids)} legacy mock shifts. Backup: {backup_path}")

    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('legacy_mock_data_removed_v1', '1')"
    )
    conn.commit()


def seed_reference_data(conn):
    cursor = conn.cursor()
    
    # Seed Categories
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        categories = [
            (1, 'وجبات بروست', 1),
            (2, 'وجبات ميكس بروست', 2),
            (3, 'وجبات ستريبس', 3),
            (4, 'قطع بروست', 4),
            (5, 'سندوتشات بروست', 5),
            (6, 'سندوتشات برجر بروست', 6),
            (7, 'ريزو بروست', 7),
            (8, 'اضافات بروست', 8),
        ]
        cursor.executemany("INSERT INTO categories (id, name, sort_order) VALUES (?, ?, ?)", categories)
        conn.commit()
        
        # Seed Menu Items
        menu_items = [
            # 1. وجبات بروست
            ("فرخة كاملة 9 قطع", 1, 560.0, 1),
            ("نص فرخة 5 قطع", 1, 340.0, 1),
            ("ربع فرخة صدر 3 قطع", 1, 200.0, 0),
            ("ربع فرخة ورك 2 قطعة", 1, 135.0, 0),

            # 2. وجبات ميكس بروست
            ("فاميلي ميكس", 2, 550.0, 1),
            ("دينر ميكس", 2, 340.0, 0),
            ("بيج ميكس", 2, 200.0, 0),

            # 3. وجبات ستريبس
            ("10 ستريبس", 3, 450.0, 1),
            ("4 ستريبس", 3, 190.0, 1),
            ("2 ستريبس", 3, 110.0, 0),
            ("وجبة فاهيتا", 3, 100.0, 0),

            # 4. قطع بروست
            ("فاميلي بوكس 15 قطعة", 4, 799.0, 1),
            ("فاميلي بوكس 12 قطعة", 4, 640.0, 0),
            ("سوبر بوكس 6 قطع", 4, 320.0, 0),
            ("دينر بوكس 4 قطع", 4, 215.0, 0),
            ("كينج بوكس 3 قطع", 4, 160.0, 0),
            ("بيج بوكس 2 قطعة", 4, 105.0, 0),

            # 5. سندوتشات بروست
            ("سندوتش بروست", 5, 150.0, 1),
            ("سندوتش ستريبس", 5, 95.0, 1),
            ("سندوتش زنجر حار", 5, 95.0, 1),
            ("سندوتش فاهيتا", 5, 95.0, 0),
            ("سندوتش بطاطس موتزريلا", 5, 50.0, 0),
            ("سندوتش بطاطس بروست", 5, 75.0, 0),

            # 6. سندوتشات برجر بروست
            ("برجر تشيكن دبل بروست", 6, 170.0, 1),
            ("برجر تشيكن سنجل", 6, 120.0, 0),
            ("برجر لحم دبل بروست", 6, 160.0, 0),
            ("برجر لحم سنجل", 6, 110.0, 0),

            # 7. ريزو بروست
            ("طبق ريزو أرز كبير", 7, 120.0, 1),
            ("طبق ريزو بطاطس كبير", 7, 120.0, 0),
            ("طبق ريزو بطاطس وسط", 7, 90.0, 0),

            # 8. اضافات بروست
            ("باكيت بطاطس",   8, 30.0, 1),
            ("أرز بسمتي",     8, 30.0, 0),
            ("كانز بيبسي",    8, 20.0, 1),
            ("قطعة بروست",    8, 60.0, 0),
            ("قطعة ستريبس",   8, 40.0, 0),
            ("صوص بروست",     8, 20.0, 0),
            ("صوص شيدر",      8, 20.0, 0),
            ("صوص رانش",      8, 20.0, 0),
            ("علبة كول سلو",  8, 20.0, 0),
            ("صوص باربيكيو",  8, 20.0, 0),
            ("صوص سبايسي",    8, 15.0, 0),
            ("تومية",         8, 20.0, 0),
        ]
        
        # Insert menu items
        for name, category_id, base_price, is_popular in menu_items:
            cursor.execute("INSERT INTO menu_items (name, category_id, base_price, is_popular) VALUES (?, ?, ?, ?)", 
                           (name, category_id, base_price, is_popular))
        conn.commit()
        
        # Seed bread options / sizes for sandwiches (Syrian vs French/Kaiser offset +10 EGP)
        sandwiches_with_sizes = ["سندوتش بروست", "سندوتش ستريبس", "سندوتش زنجر حار", "سندوتش فاهيتا"]
        for s_name in sandwiches_with_sizes:
            cursor.execute("SELECT id FROM menu_items WHERE name=?", (s_name,))
            res = cursor.fetchone()
            if res:
                item_id = res[0]
                cursor.executemany("INSERT INTO menu_item_sizes (item_id, name, price_offset) VALUES (?, ?, ?)", [
                    (item_id, "سوري", 0.0),
                    (item_id, "فرنساوي", 10.0)
                ])
            
        # Seed general extras for Broast chicken & boxes (categories 1 and 4)
        cursor.execute("SELECT id FROM menu_items WHERE category_id IN (1, 4)")
        items = cursor.fetchall()
        for it in items:
            cursor.executemany("INSERT INTO menu_item_extras (item_id, name, price) VALUES (?, ?, ?)", [
                (it[0], "صوص شيدر إضافي", 20.0),
                (it[0], "علبة كول سلو إضافية", 20.0),
                (it[0], "تومية إضافية", 20.0)
            ])
        conn.commit()

    # Reference rows are seeded after the schema migration above. Give newly
    # seeded rows stable sync identifiers before the first website sync.
    cursor.execute("UPDATE categories SET sync_id='category-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE menu_items SET sync_id='item-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE menu_item_sizes SET sync_id='size-' || id WHERE sync_id IS NULL OR sync_id=''")
    cursor.execute("UPDATE menu_item_extras SET sync_id='extra-' || id WHERE sync_id IS NULL OR sync_id=''")
    conn.commit()

    # Seed Drivers
    cursor.execute("SELECT COUNT(*) FROM drivers")
    if cursor.fetchone()[0] == 0:
        drivers = [
            ("كريم محمد", ""),
            ("اسامه هندي", ""),
            ("عمر صلاح", ""),
        ]
        cursor.executemany("INSERT INTO drivers (name, phone) VALUES (?, ?)", drivers)
        conn.commit()

def get_business_day_start():
    """
    Returns the start datetime of the current business day.

    Logic:
    - If a shift was closed today (after 8 AM), the business day starts
      from the last shift's closed_at time.
    - Otherwise, the business day starts at 08:00 AM of the current calendar day.

    This handles restaurants that open at 8 AM and close after midnight.
    """
    from datetime import datetime
    now = datetime.now()

    # 8 AM today as the default business day start
    today_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)

    # If it's before 8 AM, "today" for business purposes started at 8 AM yesterday
    if now < today_8am:
        today_8am = today_8am - timedelta(days=1)

    try:
        conn = get_connection()
        c = conn.cursor()
        # Find the most recent closed shift (closed_at after our 8am anchor)
        c.execute(
            "SELECT closed_at FROM shifts WHERE closed_at IS NOT NULL AND closed_at >= ? ORDER BY closed_at DESC LIMIT 1",
            (today_8am.strftime("%Y-%m-%d %H:%M:%S"),)
        )
        row = c.fetchone()
        conn.close()

        if row:
            last_close = datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
            return last_close  # Business day starts from last shift closing
    except Exception:
        pass

    return today_8am  # Default: 8 AM


def run_backup(prefix="broost_pos_backup"):
    """Create a consistent SQLite backup in the backups/ folder."""
    try:
        if not os.path.exists(DB_PATH):
            return False, "Database file does not exist."
            
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
            
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"{prefix}_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        source_conn = sqlite3.connect(DB_PATH)
        backup_conn = sqlite3.connect(backup_path)
        try:
            source_conn.backup(backup_conn)
        finally:
            backup_conn.close()
            source_conn.close()
        
        # Maintain only last 10 backups to prevent infinite disk space bloat
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(f"{prefix}_")])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
                
        return True, backup_path
    except Exception as e:
        return False, str(e)


def validate_pos_backup(backup_path):
    """Validate that a file is a healthy Broost POS SQLite database."""
    path = Path(backup_path).expanduser().resolve()
    if not path.is_file():
        return False, "ملف النسخة الاحتياطية غير موجود."

    try:
        if Path(DB_PATH).resolve() == path:
            return False, "اختر نسخة احتياطية مختلفة عن قاعدة البيانات المستخدمة حاليًا."

        read_only_uri = f"{path.as_uri()}?mode=ro"
        conn = sqlite3.connect(read_only_uri, uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]).lower() != "ok":
                return False, "ملف النسخة الاحتياطية تالف أو غير مكتمل."

            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {row[0] for row in table_rows}
            required_tables = {
                "settings",
                "customers",
                "categories",
                "menu_items",
                "drivers",
                "shifts",
                "orders",
                "order_items",
            }
            missing = sorted(required_tables - tables)
            if missing:
                return False, "الملف ليس Backup صالحًا لبرنامج الكاشير."
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return False, f"تعذر قراءة النسخة الاحتياطية: {exc}"

    return True, str(path)


def restore_pos_backup(backup_path):
    """
    Replace the current database with a validated old POS backup.

    The imported copy is migrated through init_db() before it becomes live, and
    a consistent safety backup of the current database is always created first.
    """
    valid, validated_path = validate_pos_backup(backup_path)
    if not valid:
        return False, validated_path

    backup_ok, safety_backup = run_backup(prefix="pre_restore")
    if not backup_ok:
        return False, f"لم يتم الاستيراد لأن إنشاء نسخة أمان للداتا الحالية فشل: {safety_backup}"

    staging_path = None
    original_db_path = DB_PATH
    try:
        live_db_dir = os.path.dirname(os.path.abspath(original_db_path))
        os.makedirs(live_db_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="broost_restore_", suffix=".db", dir=live_db_dir, delete=False
        ) as staging_file:
            staging_path = staging_file.name

        source_uri = f"{Path(validated_path).as_uri()}?mode=ro"
        source_conn = sqlite3.connect(source_uri, uri=True)
        staging_conn = sqlite3.connect(staging_path)
        try:
            source_conn.backup(staging_conn)
        finally:
            staging_conn.close()
            source_conn.close()

        # Upgrade the imported copy to the current application schema while it
        # is still isolated from the live database.
        globals()["DB_PATH"] = staging_path
        try:
            init_db()
        finally:
            globals()["DB_PATH"] = original_db_path

        migrated_conn = sqlite3.connect(staging_path)
        try:
            integrity = migrated_conn.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]).lower() != "ok":
                raise sqlite3.DatabaseError("integrity_check failed after migration")
        finally:
            migrated_conn.close()

        # Atomic replacement: if Windows reports an open handle, os.replace
        # fails and the original database remains untouched.
        os.replace(staging_path, original_db_path)
        staging_path = None
        return True, {
            "imported_from": validated_path,
            "safety_backup": safety_backup,
        }
    except Exception as exc:
        globals()["DB_PATH"] = original_db_path
        return False, f"فشل تحويل واستيراد النسخة الاحتياطية: {exc}"
    finally:
        if staging_path and os.path.exists(staging_path):
            try:
                os.remove(staging_path)
            except OSError:
                pass

if __name__ == "__main__":
    init_db()
    print("Database initialised successfully.")
