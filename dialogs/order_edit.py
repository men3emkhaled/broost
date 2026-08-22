# -*- coding: utf-8 -*-
"""Broost POS - Order Edit Dialog"""
import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QComboBox, QMessageBox,
    QLineEdit, QTabWidget, QGridLayout, QSizePolicy
)
import database
from core.display_text import pos_text
from core.order_finance import reconcile_order_finance
from styles import STYLE_SHEET
from dialogs.receipt import ReceiptSimDialog


class OrderEditDialog(QDialog):
    """Edit pending orders: add items by category, adjust quantities, and recalculate totals."""

    def __init__(self, order_id, parent=None):
        super().__init__(parent)
        self.order_id = order_id
        self.parent_dashboard = parent
        self.setWindowTitle(f"تعديل الطلب #{self.order_id}")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        
        # Screen resolution check
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_size = screen.size() if screen else None
        is_small = screen_size and (screen_size.width() <= 1366 or screen_size.height() <= 768)
        if is_small:
            self.setFixedSize(1120, 560)
        else:
            self.setFixedSize(1180, 680)

        self.setStyleSheet(STYLE_SHEET)

        self.items = []
        self.delivery_fee = 0.0
        self.payment_method = "CASH"
        self.channel = "CASHIER"
        self.status = "PENDING"
        self.driver_id = None
        self.shift_id = None
        self.original_total = 0.0
        self.customer_name = ""
        self.customer_phone = ""
        self.cash_paid = 0.0
        self.active_input = None

        self.init_ui()
        self.load_order_details()
        self.load_menu_categories()
        self.recalculate()

    # ─────────────────────────────────────────────
    #  UI BUILD
    # ─────────────────────────────────────────────
    def init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── LEFT PANEL: Category tabs + item buttons ──
        left_panel = QFrame(self)
        left_panel.setStyleSheet("background: #f8fafc; border-right: 1px solid #e5e7eb;")
        left_panel.setFixedWidth(540)
        left_lyt = QVBoxLayout(left_panel)
        left_lyt.setContentsMargins(14, 14, 14, 14)
        left_lyt.setSpacing(10)

        # Header
        left_header = QHBoxLayout()
        title_lbl = QLabel(f"✏️  تعديل الطلب #{self.order_id}", left_panel)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4;")
        left_header.addWidget(title_lbl)
        left_header.addStretch()
        btn_close = QPushButton("✕", left_panel)
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet("QPushButton{background:#f3f4f6;color:#4b5563;border:1px solid #e5e7eb;border-radius:6px;font-weight:bold;font-size:14px;padding:0;}QPushButton:hover{background:#fee2e2;color:#dc2626;border-color:#fca5a5;}")
        btn_close.clicked.connect(self.reject)
        left_header.addWidget(btn_close)
        left_lyt.addLayout(left_header)

        # Customer info
        self.lbl_cust_info = QLabel("👤 جاري تحميل بيانات العميل...", left_panel)
        self.lbl_cust_info.setStyleSheet("color:#4b5563;font-size:11px;font-weight:bold;padding:4px 0;")
        left_lyt.addWidget(self.lbl_cust_info)

        # Category tabs
        self.category_tabs = QTabWidget(left_panel)
        self.category_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff; }
            QTabBar::tab {
                background: #f3f4f6; color: #374151; padding: 7px 14px;
                border-radius: 6px; margin: 2px; font-size: 12px; font-weight: bold;
            }
            QTabBar::tab:selected { background: #0078d4; color: #ffffff; }
            QTabBar::tab:hover:!selected { background: #e0ecff; }
        """)
        left_lyt.addWidget(self.category_tabs)

        root.addWidget(left_panel)

        # ── RIGHT PANEL: Cart + Totals + Actions ──
        right_panel = QFrame(self)
        right_panel.setStyleSheet("background: #ffffff;")
        right_lyt = QVBoxLayout(right_panel)
        right_lyt.setContentsMargins(14, 14, 14, 14)
        right_lyt.setSpacing(10)

        right_title = QLabel("🛒  محتويات الطلب الحالية", right_panel)
        right_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #111827;")
        right_lyt.addWidget(right_title)

        # Scroll area for cart items
        self.scroll = QScrollArea(right_panel)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;")
        self.scroll_widget = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_widget)
        self.items_layout.setContentsMargins(8, 8, 8, 8)
        self.items_layout.setSpacing(6)
        self.scroll.setWidget(self.scroll_widget)
        right_lyt.addWidget(self.scroll)

        # Totals box
        calc_box = QFrame(right_panel)
        calc_box.setStyleSheet("background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:6px;")
        calc_lyt = QVBoxLayout(calc_box)
        calc_lyt.setSpacing(6)

        r_sub = QHBoxLayout()
        r_sub.addWidget(QLabel("المجموع الفرعي:", calc_box))
        r_sub.addStretch()
        self.lbl_subtotal = QLabel("0.00 ج", calc_box)
        self.lbl_subtotal.setStyleSheet("color:#111827;font-weight:bold;")
        r_sub.addWidget(self.lbl_subtotal)
        calc_lyt.addLayout(r_sub)

        r_disc = QHBoxLayout()
        r_disc.addWidget(QLabel("خصم (ج.م):", calc_box))
        r_disc.addStretch()
        self.txt_discount = QLineEdit(calc_box)
        self.txt_discount.setFixedWidth(90)
        self.txt_discount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_discount.setStyleSheet("QLineEdit{background:#fff;border:1px solid #d1d5db;border-radius:4px;color:#111827;padding:3px;font-weight:bold;}QLineEdit:focus{border-color:#0078d4;}")
        self.txt_discount.textChanged.connect(self.recalculate)
        r_disc.addWidget(self.txt_discount)
        calc_lyt.addLayout(r_disc)

        r_grand = QHBoxLayout()
        r_grand.addWidget(QLabel("الإجمالي الكلي:", calc_box))
        r_grand.addStretch()
        self.lbl_grand = QLabel("0.00 ج", calc_box)
        self.lbl_grand.setStyleSheet("color:#107c10;font-weight:bold;font-size:14px;")
        r_grand.addWidget(self.lbl_grand)
        calc_lyt.addLayout(r_grand)

        sep = QFrame(calc_box)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:#e5e7eb;max-height:1px;border:none;")
        calc_lyt.addWidget(sep)

        pay_row = QHBoxLayout()
        pay_row.addWidget(QLabel("💵 الكاش المدفوع:", calc_box))
        self.txt_paid = QLineEdit(calc_box)
        self.txt_paid.setFixedWidth(90)
        self.txt_paid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_paid.setStyleSheet("QLineEdit{background:#fff;border:1px solid #d1d5db;border-radius:4px;color:#111827;padding:3px;font-weight:bold;}QLineEdit:focus{border-color:#0078d4;}")
        self.txt_paid.textChanged.connect(self.recalculate)
        pay_row.addWidget(self.txt_paid)
        calc_lyt.addLayout(pay_row)

        chg_row = QHBoxLayout()
        self.lbl_change_title = QLabel("الباقي للعميل:", calc_box)
        chg_row.addWidget(self.lbl_change_title)
        chg_row.addStretch()
        self.lbl_change_due = QLabel("0.00 ج", calc_box)
        self.lbl_change_due.setStyleSheet("color:#107c10;font-weight:bold;")
        chg_row.addWidget(self.lbl_change_due)
        calc_lyt.addLayout(chg_row)

        right_lyt.addWidget(calc_box)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("تراجع وإلغاء", right_panel)
        btn_cancel.setFixedHeight(38)
        btn_cancel.setStyleSheet("QPushButton{background:#fff;color:#374151;border:1px solid #d1d5db;border-radius:6px;font-size:12px;font-weight:bold;}QPushButton:hover{background:#f9fafb;}")
        btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("💾 حفظ وإعادة الطباعة", right_panel)
        self.btn_save.setFixedHeight(38)
        self.btn_save.setStyleSheet("QPushButton{background:#0078d4;color:white;border:none;border-radius:6px;font-size:12px;font-weight:bold;}QPushButton:hover{background:#106ebe;}")
        self.btn_save.clicked.connect(self.save_changes)

        btn_row.addWidget(btn_cancel, stretch=1)
        btn_row.addWidget(self.btn_save, stretch=2)
        right_lyt.addLayout(btn_row)

        root.addWidget(right_panel)

        # Override focusInEvent to track active input field
        orig_focus_in_discount = self.txt_discount.focusInEvent
        orig_focus_in_paid = self.txt_paid.focusInEvent
        
        def handle_discount_focus(event):
            self.active_input = self.txt_discount
            self.lbl_active_field.setText("الحقل النشط: الخصم")
            orig_focus_in_discount(event)
            
        def handle_paid_focus(event):
            self.active_input = self.txt_paid
            self.lbl_active_field.setText("الحقل النشط: الكاش المدفوع")
            orig_focus_in_paid(event)
            
        self.txt_discount.focusInEvent = handle_discount_focus
        self.txt_paid.focusInEvent = handle_paid_focus

        # Default active input
        self.active_input = self.txt_paid

        # ── KEYPAD PANEL on the far right ──
        keypad_panel = QFrame(self)
        keypad_panel.setStyleSheet("background: #f8fafc; border-left: 1px solid #e5e7eb;")
        keypad_panel.setFixedWidth(220)
        keypad_lyt = QVBoxLayout(keypad_panel)
        keypad_lyt.setContentsMargins(14, 14, 14, 14)
        keypad_lyt.setSpacing(12)

        # Title for keypad
        keypad_title = QLabel("⌨️ لوحة الأرقام", keypad_panel)
        keypad_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0078d4;")
        keypad_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keypad_lyt.addWidget(keypad_title)

        # Active input indicator label
        self.lbl_active_field = QLabel("الحقل النشط: الكاش المدفوع", keypad_panel)
        self.lbl_active_field.setStyleSheet("font-size: 11px; color: #4b5563; font-weight: bold;")
        self.lbl_active_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keypad_lyt.addWidget(self.lbl_active_field)

        # Grid for keypad
        grid_widget = QWidget(keypad_panel)
        grid_lyt = QGridLayout(grid_widget)
        grid_lyt.setSpacing(6)
        grid_lyt.setContentsMargins(0, 0, 0, 0)

        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('.', 3, 0), ('0', 3, 1), ('←', 3, 2),
        ]

        for text, row, col in keys:
            btn = QPushButton(text, grid_widget)
            btn.setFixedSize(60, 52)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 18px; font-weight: bold; background: #ffffff;
                    border: 1px solid #d1d5db; color: #1a1a1a; border-radius: 8px;
                }
                QPushButton:hover { background: #f3f4f6; }
                QPushButton:pressed { background: #e5e7eb; }
            """)

            if text == '←':
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 18px; font-weight: bold; background: #ffe3e3;
                        color: #c30000; border: 1px solid #fbcaca; border-radius: 8px;
                    }
                    QPushButton:hover { background: #c30000; color: white; }
                    QPushButton:pressed { background: #990000; color: white; }
                """)
                btn.clicked.connect(lambda checked: self.press_keypad('←'))
            else:
                btn.clicked.connect(lambda checked, t=text: self.press_keypad(t))

            grid_lyt.addWidget(btn, row, col)

        # 'مسح' button spanning 3 columns at the bottom
        btn_clear = QPushButton('مسح كامل', grid_widget)
        btn_clear.setFixedHeight(48)
        btn_clear.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_clear.setStyleSheet("""
            QPushButton {
                font-size: 14px; font-weight: bold; background: #fff4ce;
                color: #8a6600; border: 1px solid #fde79a; border-radius: 8px;
            }
            QPushButton:hover { background: #8a6600; color: white; }
            QPushButton:pressed { background: #6b5000; color: white; }
        """)
        btn_clear.clicked.connect(lambda checked: self.press_keypad('مسح'))
        grid_lyt.addWidget(btn_clear, 4, 0, 1, 3)

        keypad_lyt.addWidget(grid_widget)
        keypad_lyt.addStretch()

        root.addWidget(keypad_panel)

    # ─────────────────────────────────────────────
    #  DATA LOADING
    # ─────────────────────────────────────────────
    def load_order_details(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT o.delivery_fee, o.payment_method, o.cash_paid, o.change_due,
                   cust.name, cust.phone, COALESCE(o.discount, 0.0), o.total,
                   o.channel, o.status, o.driver_id, o.shift_id
            FROM orders o
            LEFT JOIN customers cust ON o.customer_id = cust.id
            WHERE o.id=?
        """, (self.order_id,))
        o_data = c.fetchone()
        if o_data:
            self.delivery_fee = o_data[0] or 0.0
            self.payment_method = o_data[1] or "CASH"
            self.cash_paid = o_data[2] or 0.0
            self.customer_name = o_data[4] or "عميل صالة"
            self.customer_phone = o_data[5] or ""
            discount_val = o_data[6] or 0.0
            self.original_total = o_data[7] or 0.0
            self.channel = o_data[8] or "CASHIER"
            self.status = o_data[9] or "PENDING"
            self.driver_id = o_data[10]
            self.shift_id = o_data[11]
            pay_label = "كاش نقدي" if self.payment_method == "CASH" else "فيزا / محفظة"
            self.lbl_cust_info.setText(
                f"👤 {self.customer_name}   |   💳 {pay_label}"
                + (f"   |   📞 {self.customer_phone}" if self.customer_phone else "")
            )
            self.txt_paid.setText(f"{self.cash_paid:.2f}")
            self.txt_discount.setText(f"{discount_val:.2f}")

        c.execute("""
            SELECT oi.menu_item_id, COALESCE(oi.item_name, m.name), oi.size_name, oi.quantity, oi.price,
                   oi.extras_json, m.category_id
            FROM order_items oi
            LEFT JOIN menu_items m ON oi.menu_item_id = m.id
            WHERE oi.order_id=?
        """, (self.order_id,))
        for m_id, name, size, qty, price, ext_json, cat_id in c.fetchall():
            extras = {}
            if ext_json:
                try:
                    extras = json.loads(ext_json)
                except Exception:
                    pass
            extras = {pos_text(key): value for key, value in extras.items()}
            self.items.append({
                "id": m_id, "name": pos_text(name), "size": pos_text(size) or "عادي",
                "qty": qty, "price": price, "extras": extras,
                "category_id": cat_id
            })
        conn.close()
        self.refresh_items_display()

    def load_menu_categories(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name FROM categories ORDER BY sort_order ASC")
        categories = c.fetchall()
        c.execute("SELECT id, category_id, name, base_price FROM menu_items WHERE is_available=1 ORDER BY name ASC")
        all_items = c.fetchall()
        conn.close()

        for cat_id, cat_name in categories:
            cat_items = [it for it in all_items if it[1] == cat_id]
            if not cat_items:
                continue

            tab_widget = QWidget()
            tab_scroll = QScrollArea()
            tab_scroll.setWidgetResizable(True)
            tab_scroll.setStyleSheet("border: none; background: transparent;")

            grid_container = QWidget()
            grid = QGridLayout(grid_container)
            grid.setContentsMargins(8, 8, 8, 8)
            grid.setSpacing(8)

            for idx, (item_id, _, item_name, base_price) in enumerate(cat_items):
                display_item_name = pos_text(item_name)
                row, col = divmod(idx, 3)
                btn = QPushButton(f"{display_item_name}\n{base_price:.0f} ج.م", grid_container)
                btn.setFixedHeight(56)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setStyleSheet("""
                    QPushButton {
                        background: #ffffff;
                        color: #111827;
                        border: 1px solid #d1d5db;
                        border-radius: 8px;
                        font-size: 11px;
                        font-weight: bold;
                        padding: 4px;
                    }
                    QPushButton:hover {
                        background: #e0ecff;
                        border-color: #0078d4;
                        color: #0078d4;
                    }
                    QPushButton:pressed {
                        background: #0078d4;
                        color: #ffffff;
                    }
                """)
                btn.clicked.connect(
                    lambda checked, iid=item_id, iname=display_item_name, iprice=base_price:
                    self.add_item_by_id(iid, iname, iprice)
                )
                grid.addWidget(btn, row, col)

            tab_scroll.setWidget(grid_container)

            tab_lyt = QVBoxLayout(tab_widget)
            tab_lyt.setContentsMargins(0, 0, 0, 0)
            tab_lyt.addWidget(tab_scroll)

            self.category_tabs.addTab(tab_widget, pos_text(cat_name))

    # ─────────────────────────────────────────────
    #  CART OPERATIONS
    # ─────────────────────────────────────────────
    def add_item_by_id(self, item_id, name, base_price):
        # If already in cart, increment qty
        for item in self.items:
            if item["id"] == item_id:
                item["qty"] += 1
                self.refresh_items_display()
                self.recalculate()
                return

        self.items.append({
            "id": item_id, "name": name, "size": "عادي",
            "qty": 1, "price": base_price, "extras": {},
            "category_id": None
        })
        self.refresh_items_display()
        self.recalculate()

    def refresh_items_display(self):
        while self.items_layout.count():
            child = self.items_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for index, item in enumerate(self.items):
            row_frame = QFrame(self.scroll_widget)
            row_frame.setObjectName("ItemRow")
            row_frame.setStyleSheet("""
                QFrame#ItemRow {
                    background: #ffffff;
                    border: 1px solid #e5e7eb;
                    border-radius: 6px;
                }
            """)
            r_lyt = QHBoxLayout(row_frame)
            r_lyt.setContentsMargins(8, 5, 8, 5)
            r_lyt.setSpacing(6)

            lbl_name = QLabel(pos_text(item['name']), row_frame)
            lbl_name.setStyleSheet("color:#111827;font-weight:bold;font-size:12px;border:none;background:transparent;")
            lbl_name.setWordWrap(True)
            r_lyt.addWidget(lbl_name, stretch=1)

            btn_minus = QPushButton("−", row_frame)
            btn_minus.setFixedSize(26, 26)
            btn_minus.setStyleSheet("QPushButton{background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;border-radius:4px;font-weight:bold;font-size:15px;padding:0;}QPushButton:hover{background:#b91c1c;color:white;}")
            btn_minus.clicked.connect(lambda checked, idx=index: self.adjust_qty(idx, -1))
            r_lyt.addWidget(btn_minus)

            lbl_qty = QLabel(str(item["qty"]), row_frame)
            lbl_qty.setStyleSheet("color:#111827;font-weight:900;font-size:14px;border:none;background:transparent;")
            lbl_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_qty.setFixedWidth(24)
            r_lyt.addWidget(lbl_qty)

            btn_plus = QPushButton("+", row_frame)
            btn_plus.setFixedSize(26, 26)
            btn_plus.setStyleSheet("QPushButton{background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;border-radius:4px;font-weight:bold;font-size:15px;padding:0;}QPushButton:hover{background:#15803d;color:white;}")
            btn_plus.clicked.connect(lambda checked, idx=index: self.adjust_qty(idx, 1))
            r_lyt.addWidget(btn_plus)

            lbl_price = QLabel(f"{item['price'] * item['qty']:.0f} ج", row_frame)
            lbl_price.setStyleSheet("color:#107c10;font-weight:bold;font-size:12px;border:none;background:transparent;")
            lbl_price.setFixedWidth(55)
            lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            r_lyt.addWidget(lbl_price)

            btn_del = QPushButton("✕", row_frame)
            btn_del.setFixedSize(26, 26)
            btn_del.setStyleSheet("QPushButton{background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;border-radius:4px;font-weight:bold;font-size:12px;padding:0;}QPushButton:hover{background:#dc2626;color:white;}")
            btn_del.clicked.connect(lambda checked, idx=index: self.remove_item(idx))
            r_lyt.addWidget(btn_del)

            self.items_layout.addWidget(row_frame)

        self.items_layout.addStretch()

    def adjust_qty(self, idx, amount):
        self.items[idx]["qty"] += amount
        if self.items[idx]["qty"] <= 0:
            self.items.pop(idx)
        self.refresh_items_display()
        self.recalculate()

    def remove_item(self, idx):
        self.items.pop(idx)
        self.refresh_items_display()
        self.recalculate()

    def recalculate(self):
        subtotal = sum(item["price"] * item["qty"] for item in self.items)
        try:
            discount = float(self.txt_discount.text().strip()) if self.txt_discount.text().strip() else 0.0
        except ValueError:
            discount = 0.0
        grand_total = max(0.0, subtotal + self.delivery_fee - discount)

        self.lbl_subtotal.setText(f"{subtotal:.2f} ج")
        self.lbl_grand.setText(f"{grand_total:.2f} ج")

        try:
            paid = float(self.txt_paid.text().strip())
        except ValueError:
            paid = 0.0

        change = paid - grand_total
        if change >= 0:
            self.lbl_change_title.setText("الباقي للعميل:")
            self.lbl_change_due.setText(f"{change:.2f} ج")
            self.lbl_change_due.setStyleSheet("color:#107c10;font-weight:bold;border:none;background:transparent;")
        else:
            self.lbl_change_title.setText("⚠️ متبقي للتحصيل:")
            self.lbl_change_due.setText(f"{abs(change):.2f} ج")
            self.lbl_change_due.setStyleSheet("color:#b91c1c;font-weight:bold;border:none;background:transparent;")

    # ─────────────────────────────────────────────
    #  SAVE
    # ─────────────────────────────────────────────
    def save_changes(self):
        if not self.items:
            QMessageBox.warning(self, "طلب فارغ", "لا يمكن حفظ الطلب وهو فارغ. أضف وجبات أو ألغِ التعديل.")
            return

        subtotal = sum(item["price"] * item["qty"] for item in self.items)
        try:
            discount = float(self.txt_discount.text().strip()) if self.txt_discount.text().strip() else 0.0
        except ValueError:
            discount = 0.0
        grand_total = max(0.0, subtotal + self.delivery_fee - discount)

        try:
            paid = float(self.txt_paid.text().strip())
        except ValueError:
            paid = grand_total
        change = max(0.0, paid - grand_total)

        conn = database.get_connection()
        c = conn.cursor()

        c.execute("""
            UPDATE orders
            SET subtotal=?, discount=?, total=?, cash_paid=?, change_due=?
            WHERE id=?
        """, (subtotal, discount, grand_total, paid, change, self.order_id))

        c.execute("DELETE FROM order_items WHERE order_id=?", (self.order_id,))

        for item in self.items:
            c.execute("""
                INSERT INTO order_items (order_id, menu_item_id, item_name, size_name, quantity, price, extras_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self.order_id, item["id"], item["name"], item["size"], item["qty"],
                  item["price"], json.dumps(item["extras"])))

        reconcile_order_finance(
            conn,
            self.order_id,
            fallback_shift_id=self.shift_id,
        )

        conn.commit()
        conn.close()
        self.original_total = grand_total

        if self.parent_dashboard:
            cashier_receipt = self.parent_dashboard.generate_receipt_text(self.order_id, "نسخة الكاشير")
            kitchen_receipt = self.parent_dashboard.generate_receipt_text(self.order_id, "نسخة المطبخ")
            self.parent_dashboard.load_pending_delivery_orders()
            self.parent_dashboard.ensure_active_shift()
            
            from core import config
            if config.PRINTER_ONLINE:
                from core.printing import print_text_to_printer
                print_text_to_printer(cashier_receipt, self.parent_dashboard)
                print_text_to_printer(kitchen_receipt, self.parent_dashboard)
            else:
                psim = ReceiptSimDialog(self.order_id, cashier_receipt, kitchen_receipt, self.parent_dashboard)
                psim.exec()

        self.accept()

    def press_keypad(self, char):
        if not self.active_input:
            return
        
        current = self.active_input.text()
        
        # If the field is selected (all text highlighted), clear it first
        if self.active_input.hasSelectedText():
            current = ""
            self.active_input.clear()

        if char == '.':
            if '.' in current:
                return  # Only one decimal point allowed
            if not current:
                current = "0"
            self.active_input.setText(current + '.')
        elif char == '←':
            if current:
                self.active_input.setText(current[:-1])
        elif char == 'مسح':
            self.active_input.clear()
        else:
            if current == "0":
                self.active_input.setText(char)
            else:
                self.active_input.setText(current + char)
