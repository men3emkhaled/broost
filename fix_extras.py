import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('broost_pos.db')
c = conn.cursor()

# Delete existing extras items (category 8)
c.execute('DELETE FROM menu_items WHERE category_id=8')
print('Deleted old extras items')

# Insert new extras items matching the menu image (12 items)
new_items = [
    (31, 8, 'باكيت بطاطس',   30.0, 1, 1),
    (32, 8, 'أرز بسمتي',     30.0, 1, 0),
    (33, 8, 'كانز بيبسي',    20.0, 1, 1),
    (34, 8, 'قطعة بروست',    60.0, 1, 0),
    (35, 8, 'قطعة ستريبس',   40.0, 1, 0),
    (36, 8, 'صوص بروست',     20.0, 1, 0),
    (37, 8, 'صوص شيدر',      20.0, 1, 0),
    (38, 8, 'صوص رانش',      20.0, 1, 0),
    (39, 8, 'علبة كول سلو',  20.0, 1, 0),
    (40, 8, 'صوص باربيكيو',  20.0, 1, 0),
    (41, 8, 'صوص سبايسي',    15.0, 1, 0),
    (42, 8, 'تومية',         20.0, 1, 0),
]

c.executemany(
    'INSERT INTO menu_items (id, category_id, name, base_price, is_available, is_popular) VALUES (?,?,?,?,?,?)',
    new_items
)

# Update autoincrement sequence
c.execute("DELETE FROM sqlite_sequence WHERE name='menu_items'")
c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('menu_items', 42)")

conn.commit()
conn.close()
print(f'Done! Inserted {len(new_items)} extras items.')
