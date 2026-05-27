import sqlite3
import os
import sys
import shutil
from datetime import datetime, timedelta
import json
import random

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
    
    # 7. Drivers Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # 8. Shifts Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # 10. Order Items Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            menu_item_id INTEGER,
            size_name TEXT,
            quantity INTEGER,
            price REAL,
            extras_json TEXT, -- JSON array of extra names and prices
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
        )
    """)
    
    conn.commit()
    
    # Seed default configurations & passwords
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("app_password", "123"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("delete_password", "456"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("printer_online", "1"))
        cursor.execute("INSERT INTO settings VALUES (?, ?)", ("delivery_fee", "15"))
        conn.commit()
        
    seed_mock_data(conn)
    conn.close()

def seed_mock_data(conn):
    cursor = conn.cursor()
    
    # Seed Categories
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        categories = [
            ("وجبات بروست", 1),
            ("سندوتشات بروست", 2),
            ("وجبات ستربس", 3),
            ("قطع بروست", 4),
            ("برجر بروست", 5),
            ("ريزو وبطاطس", 6),
            ("وجبات ميكس", 7),
            ("إضافات بروست", 8)
        ]
        cursor.executemany("INSERT INTO categories (name, sort_order) VALUES (?, ?)", categories)
        conn.commit()
        
        # Seed Menu Items
        menu_items = [
            # وجبات بروست
            ("فرخة كاملة 9 قطع", 1, 560.0, 1),
            ("نص فرخة 5 قطع", 1, 340.0, 1),
            ("ربع فرخة صدر 3 قطع", 1, 200.0, 0),
            ("ربع فرخة ورك 2 قطعه", 1, 135.0, 0),
            
            # سندوتشات بروست (سوري/فرنساوي)
            ("سندوتش بروست", 2, 150.0, 1),
            ("سندوتش ستربس", 2, 95.0, 1),
            ("سندوتش زنجر حار", 2, 95.0, 1),
            ("سندوتش فاهيتا", 2, 95.0, 0),
            ("سندوتش بطاطس موتزريلا", 2, 50.0, 0),
            ("سندوتش بطاطس بروست", 2, 75.0, 0),
            
            # وجبات ستربس
            ("10 ستربس", 3, 450.0, 1),
            ("4 ستربس", 3, 190.0, 1),
            ("2 ستربس", 3, 110.0, 0),
            ("وجبة فاهيتا", 3, 100.0, 0),
            
            # قطع بروست
            ("فاميلي بوكس 15 قطعة", 4, 799.0, 1),
            ("فاميلي بوكس 12 قطعة", 4, 640.0, 0),
            ("سوبر بوكس 6 قطع", 4, 320.0, 0),
            ("دينر بوكس 4 قطع", 4, 215.0, 0),
            ("كينج بوكس 3 قطع", 4, 160.0, 0),
            ("بيج بوكس 2 قطع", 4, 105.0, 0),
            
            # برجر بروست
            ("سندوتش برجر تشيكن دبل", 5, 170.0, 1),
            ("سندوتش برجر تشيكن سنجل", 5, 120.0, 0),
            ("سندوتش تشيز برجر لحم دبل", 5, 160.0, 0),
            ("سندوتش تشيز برجر لحم سنجل", 5, 110.0, 0),
            
            # ريزو وبطاطس
            ("طبق ريزو أرز كبير", 6, 120.0, 1),
            ("طبق ريزو بطاطس كبير", 6, 120.0, 0),
            ("طبق ريزو بطاطس وسط", 6, 90.0, 0),
            
            # وجبات ميكس
            ("فاميلي ميكس", 7, 560.0, 1),
            ("دينر ميكس", 7, 340.0, 0),
            ("بيج ميكس", 7, 200.0, 0),
            
            # إضافات بروست
            ("باكت بطاطس", 8, 30.0, 1),
            ("أرز بسمتي", 8, 30.0, 0),
            ("كانز بيبسي", 8, 20.0, 1),
            ("قطعة بروست", 8, 50.0, 0),
            ("قطعة ستربس", 8, 40.0, 0),
            ("صوص بروست", 8, 20.0, 0),
            ("صوص شيدر", 8, 20.0, 0),
            ("صوص رانش", 8, 20.0, 0),
            ("علبة كول سلو", 8, 20.0, 0),
            ("صوص باربيكيو", 8, 20.0, 0),
            ("صوص سبايسي", 8, 15.0, 0),
            ("تومية", 8, 20.0, 0)
        ]
        
        # Insert menu items
        for name, category_id, base_price, is_popular in menu_items:
            cursor.execute("INSERT INTO menu_items (name, category_id, base_price, is_popular) VALUES (?, ?, ?, ?)", 
                           (name, category_id, base_price, is_popular))
        conn.commit()
        
        # Seed bread options / sizes for sandwiches (Syrian vs French/Kaiser offset +10 EGP)
        sandwiches_with_sizes = ["سندوتش بروست", "سندوتش ستربس", "سندوتش زنجر حار", "سندوتش فاهيتا"]
        for s_name in sandwiches_with_sizes:
            cursor.execute("SELECT id FROM menu_items WHERE name=?", (s_name,))
            item_id = cursor.fetchone()[0]
            cursor.executemany("INSERT INTO menu_item_sizes (item_id, name, price_offset) VALUES (?, ?, ?)", [
                (item_id, "سوري", 0.0),
                (item_id, "فرنساوي", 10.0)
            ])
            
        # Seed general extras for Broast chicken & burgers
        cursor.execute("SELECT id FROM menu_items WHERE category_id IN (1, 5)")
        items = cursor.fetchall()
        for it in items:
            cursor.executemany("INSERT INTO menu_item_extras (item_id, name, price) VALUES (?, ?, ?)", [
                (it[0], "صوص شيدر إضافي", 20.0),
                (it[0], "علبة كول سلو إضافية", 20.0),
                (it[0], "تومية إضافية", 20.0)
            ])
        conn.commit()

    # Seed Drivers
    cursor.execute("SELECT COUNT(*) FROM drivers")
    if cursor.fetchone()[0] == 0:
        drivers = [
            ("أحمد علي", "01023456789"),
            ("محمد حسام", "01198765432"),
            ("محمود مصطفى", "01234567890"),
            ("كريم حسن", "01512345678")
        ]
        cursor.executemany("INSERT INTO drivers (name, phone) VALUES (?, ?)", drivers)
        conn.commit()

    # Seed Customers
    cursor.execute("SELECT COUNT(*) FROM customers")
    if cursor.fetchone()[0] == 0:
        customers = [
            ("01011111111", "عبد المنعم خالد", "الدقي - شارع التحرير - عمارة 15 دور 4 شقة 8"),
            ("01122222222", "ياسر أحمد", "مدينة نصر - عباس العقاد - خلف مطعم أم حسن"),
            ("01233333333", "سارة مصطفى", "مصر الجديدة - ميدان تريومف - بجوار صيدلية العزبي"),
            ("01544444444", "طارق محمد", "المعادي - دجلة - شارع 9 - عمارة 200")
        ]
        cursor.executemany("INSERT INTO customers (phone, name, address) VALUES (?, ?, ?)", customers)
        conn.commit()
        
    # Generate 30 days of mock history for premium reports
    cursor.execute("SELECT COUNT(*) FROM orders")
    if cursor.fetchone()[0] == 0:
        print("[Database] Generating 30 days of mock order history for reports...")
        generate_historical_orders(conn)

def generate_historical_orders(conn):
    cursor = conn.cursor()
    
    # Get active components
    cursor.execute("SELECT id, name, base_price FROM menu_items WHERE is_available=1")
    menu_items = cursor.fetchall()
    
    cursor.execute("SELECT id FROM customers")
    customer_ids = [r[0] for r in cursor.fetchall()]
    
    cursor.execute("SELECT id FROM drivers")
    driver_ids = [r[0] for r in cursor.fetchall()]
    
    # 30 Days loop
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=30)
    
    current_date = start_date
    shift_id = 1
    
    while current_date <= end_date:
        # Create a shift for this day
        opened_at = current_date.replace(hour=12, minute=0, second=0)
        closed_at = current_date.replace(hour=23, minute=59, second=0)
        
        cursor.execute("""
            INSERT INTO shifts (opened_at, closed_at, expected_cash, actual_cash)
            VALUES (?, ?, 0, 0)
        """, (opened_at, closed_at))
        shift_id = cursor.lastrowid
        
        # Create random orders for this day (between 15 and 45 orders)
        num_orders = random.randint(15, 45)
        
        day_cash = 0.0
        day_visa = 0.0
        day_wallet = 0.0
        day_sales = 0.0
        
        for _ in range(num_orders):
            # Hour peak simulation (more orders between 5 PM and 10 PM)
            if random.random() < 0.7:
                hour = random.randint(17, 22)
            else:
                hour = random.choice([12, 13, 14, 15, 16, 23])
            
            minute = random.randint(0, 59)
            order_time = current_date.replace(hour=hour, minute=minute, second=0)
            
            # Select random customer
            customer_id = random.choice(customer_ids)
            
            # Channel distribution: 60% Delivery, 40% Cashier
            channel = "DELIVERY" if random.random() < 0.6 else "CASHIER"
            payment_method = random.choice(["CASH", "VISA", "WALLET"])
            
            # Select driver for delivery
            driver_id = random.choice(driver_ids) if channel == "DELIVERY" else None
            delivery_fee = 15.0 if channel == "DELIVERY" else 0.0
            
            # Items in order
            subtotal = 0.0
            items_to_add = []
            
            num_items = random.randint(1, 4)
            for _ in range(num_items):
                item = random.choice(menu_items)
                qty = random.randint(1, 2)
                item_price = item[2]
                
                # Sizes/extras simulation
                size_name = random.choice(["عادي", "حار (سبايسي)"]) if "بروست" in item[1] else "عادي"
                size_offset = 10.0 if size_name == "حار (سبايسي)" else 0.0
                
                extras = []
                if random.random() < 0.3:
                    extras.append({"name": "صوص بروست الخاص", "price": 10.0})
                if random.random() < 0.2:
                    extras.append({"name": "ثومية إضافية", "price": 8.0})
                
                single_item_total = item_price + size_offset + sum(ex["price"] for ex in extras)
                subtotal += (single_item_total * qty)
                
                items_to_add.append((item[0], size_name, qty, single_item_total, json.dumps(extras)))
            
            total = subtotal + delivery_fee
            
            cash_paid = 0.0
            change_due = 0.0
            if payment_method == "CASH":
                presets = [50, 100, 200, 500, 1000]
                possible_paid = [p for p in presets if p >= total]
                cash_paid = random.choice(possible_paid) if possible_paid else total
                change_due = cash_paid - total
                
                day_cash += total
            elif payment_method == "VISA":
                day_visa += total
            else:
                day_wallet += total
                
            day_sales += total
            
            # Insert Order
            cursor.execute("""
                INSERT INTO orders (customer_id, channel, payment_method, subtotal, delivery_fee, total, cash_paid, change_due, driver_id, status, shift_id, created_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?)
            """, (customer_id, channel, payment_method, subtotal, delivery_fee, total, cash_paid, change_due, driver_id, shift_id, order_time, order_time))
            order_id = cursor.lastrowid
            
            # Insert Order Items
            for o_item in items_to_add:
                cursor.execute("""
                    INSERT INTO order_items (order_id, menu_item_id, size_name, quantity, price, extras_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (order_id, o_item[0], o_item[1], o_item[2], o_item[3], o_item[4]))
        
        # Update shift totals
        cursor.execute("""
            UPDATE shifts 
            SET expected_cash = ?, actual_cash = ?, cash_sales = ?, visa_sales = ?, wallet_sales = ?, total_sales = ?
            WHERE id = ?
        """, (day_cash, day_cash, day_cash, day_visa, day_wallet, day_sales, shift_id))
        
        current_date += timedelta(days=1)
        
    conn.commit()

def run_backup():
    """Create an automated daily SQLite database backup file in the backups/ folder."""
    try:
        if not os.path.exists(DB_PATH):
            return False, "Database file does not exist."
            
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
            
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"broost_pos_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        shutil.copy2(DB_PATH, backup_path)
        
        # Maintain only last 10 backups to prevent infinite disk space bloat
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("broost_pos_backup_")])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
                
        return True, backup_path
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    init_db()
    print("Database initialised successfully.")
