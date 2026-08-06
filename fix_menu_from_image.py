import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('broost_pos.db')
c = conn.cursor()

print("Fixing categories and menu items based on menu image...")

# ===== STEP 1: Clear all menu items =====
c.execute('DELETE FROM menu_items')
print("Cleared all menu items.")

# ===== STEP 2: Fix categories =====
c.execute('DELETE FROM categories')
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
c.executemany('INSERT INTO categories (id, name, sort_order) VALUES (?, ?, ?)', categories)
print("Categories fixed.")

# ===== STEP 3: Insert all menu items from image =====
# (id, category_id, name, base_price, is_available, is_popular)
items = [
    # 1. وجبات بروست
    (1,  1, 'فرخة كاملة 9 قطع',      560.0, 1, 1),
    (2,  1, 'نص فرخة 5 قطع',          340.0, 1, 1),
    (3,  1, 'ربع فرخة صدر 3 قطع',     200.0, 1, 0),
    (4,  1, 'ربع فرخة ورك 2 قطعة',    135.0, 1, 0),

    # 2. وجبات ميكس بروست
    (5,  2, 'فاميلي ميكس',            550.0, 1, 1),
    (6,  2, 'دينر ميكس',              340.0, 1, 0),
    (7,  2, 'بيج ميكس',               200.0, 1, 0),

    # 3. وجبات ستريبس
    (8,  3, '10 ستريبس',              450.0, 1, 1),
    (9,  3, '4 ستريبس',               190.0, 1, 1),
    (10, 3, '2 ستريبس',               110.0, 1, 0),
    (11, 3, 'وجبة فاهيتا',            100.0, 1, 0),

    # 4. قطع بروست
    (12, 4, 'فاميلي بوكس 15 قطعة',   799.0, 1, 1),
    (13, 4, 'فاميلي بوكس 12 قطعة',   640.0, 1, 0),
    (14, 4, 'سوبر بوكس 6 قطع',        320.0, 1, 0),
    (15, 4, 'دينر بوكس 4 قطع',        215.0, 1, 0),
    (16, 4, 'كينج بوكس 3 قطع',        160.0, 1, 0),
    (17, 4, 'بيج بوكس 2 قطعة',        105.0, 1, 0),

    # 5. سندوتشات بروست
    (18, 5, 'سندوتش بروست',           150.0, 1, 1),
    (19, 5, 'سندوتش ستريبس',          95.0,  1, 1),
    (20, 5, 'سندوتش زنجر حار',        95.0,  1, 1),
    (21, 5, 'سندوتش فاهيتا',          95.0,  1, 0),
    (22, 5, 'سندوتش بطاطس موتزريلا',  50.0,  1, 0),
    (23, 5, 'سندوتش بطاطس بروست',     75.0,  1, 0),

    # 6. سندوتشات برجر بروست
    (24, 6, 'برجر تشيكن دبل بروست',   170.0, 1, 1),
    (25, 6, 'برجر تشيكن سنجل',        120.0, 1, 0),
    (26, 6, 'برجر لحم دبل بروست',     160.0, 1, 0),
    (27, 6, 'برجر لحم سنجل',          110.0, 1, 0),

    # 7. ريزو بروست
    (28, 7, 'طبق ريزو أرز كبير',       120.0, 1, 1),
    (29, 7, 'طبق ريزو بطاطس كبير',     120.0, 1, 0),
    (30, 7, 'طبق ريزو بطاطس وسط',      90.0,  1, 0),

    # 8. اضافات بروست
    (31, 8, 'باكيت بطاطس',            30.0,  1, 1),
    (32, 8, 'أرز بسمتي',              30.0,  1, 0),
    (33, 8, 'كولسلو',                  15.0,  1, 0),
    (34, 8, 'صوص',                    10.0,  1, 0),
    (35, 8, 'مايونيز',                 10.0,  1, 0),
    (36, 8, 'كاتشب',                  10.0,  1, 0),
    (37, 8, 'علبة بيبسي',              20.0,  1, 1),
    (38, 8, 'مياه معدنية',             10.0,  1, 0),
]

c.executemany(
    'INSERT INTO menu_items (id, category_id, name, base_price, is_available, is_popular) VALUES (?,?,?,?,?,?)',
    items
)
print(f"Inserted {len(items)} menu items.")

# ===== STEP 4: Reset and seed sizes & extras =====
c.execute('DELETE FROM menu_item_sizes')
c.execute('DELETE FROM menu_item_extras')

# Sizes for sandwiches (IDs 18, 19, 20, 21)
sandwiches_sizes = []
for s_id in [18, 19, 20, 21]:
    sandwiches_sizes.extend([
        (s_id, 'سوري', 0.0),
        (s_id, 'فرنساوي', 10.0)
    ])
c.executemany('INSERT INTO menu_item_sizes (item_id, name, price_offset) VALUES (?, ?, ?)', sandwiches_sizes)

# Extras for Broast meals (category 1, IDs 1-4) and Boxes (category 4, IDs 12-17)
extras = []
for item_id in list(range(1, 5)) + list(range(12, 18)):
    extras.extend([
        (item_id, 'صوص شيدر إضافي', 20.0),
        (item_id, 'علبة كول سلو إضافية', 20.0),
        (item_id, 'تومية إضافية', 20.0)
    ])
c.executemany('INSERT INTO menu_item_extras (item_id, name, price) VALUES (?, ?, ?)', extras)
print("Sizes and extras re-seeded.")

# Reset SQLite autoincrement sequence
c.execute("DELETE FROM sqlite_sequence WHERE name='menu_items'")
c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('menu_items', 38)")
c.execute("DELETE FROM sqlite_sequence WHERE name='categories'")
c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('categories', 8)")

conn.commit()
conn.close()
print("\nDone! Database updated successfully from menu image.")
