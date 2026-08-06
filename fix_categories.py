import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('broost_pos.db')
c = conn.cursor()

updates = [
    (1, '1. وجبات بروست', 1),
    (2, '2. وجبات ميكس بروست', 2),
    (3, '3. وجبات ستربس', 3),
    (4, '4. قطع بروست', 4),
    (5, '5. سندوتشات بروست', 5),
    (6, '6. سندوتشات برجر بروست', 6),
    (7, '7. ريزو بروست', 7),
    (8, '8. اضافات بروست', 8),
]

for cat_id, name, sort_order in updates:
    c.execute('SELECT COUNT(*) FROM categories WHERE id=?', (cat_id,))
    count = c.fetchone()[0]
    if count > 0:
        c.execute('UPDATE categories SET name=?, sort_order=? WHERE id=?', (name, sort_order, cat_id))
    else:
        c.execute('INSERT INTO categories (id, name, sort_order) VALUES (?, ?, ?)', (cat_id, name, sort_order))

conn.commit()
conn.close()
print('Done!')
