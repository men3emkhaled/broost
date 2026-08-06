import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('broost_pos.db')
c = conn.cursor()

# Get column names
c.execute('PRAGMA table_info(menu_items)')
cols = c.fetchall()
print("MENU ITEMS COLUMNS:", [col[1] for col in cols])

c.execute('PRAGMA table_info(categories)')
cols = c.fetchall()
print("CATEGORIES COLUMNS:", [col[1] for col in cols])

c.execute('SELECT id, name, sort_order FROM categories ORDER BY sort_order')
cats = c.fetchall()

for cat_id, cat_name, _ in cats:
    c.execute('SELECT * FROM menu_items WHERE category_id=? ORDER BY id LIMIT 3', (cat_id,))
    items = c.fetchall()
    print(f"\n[{cat_name}]")
    for item in items:
        print(f"  {item}")

conn.close()
