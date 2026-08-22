from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QWidget, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox
)
import database
from core.order_finance import reconcile_order_finance
from styles import STYLE_SHEET
from datetime import datetime


class DriversAdminDialog(QDialog):
    """View and manage driver loads/load balances and registers new delivery captains."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة طياري التوصيل")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(680, 620)
        self.setStyleSheet(STYLE_SHEET)
        
        self.init_ui()
        self.load_drivers()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        # ── Header row ──
        hdr = QHBoxLayout()
        title = QLabel("🛵  إدارة الطيارين", self)
        title.setStyleSheet("font-size: 18px; font-weight: 900; color: #0078d4; border: none;")
        hdr.addWidget(title)
        hdr.addStretch()
        btn_x = QPushButton("✕", self)
        btn_x.setFixedSize(32, 32)
        btn_x.setStyleSheet("QPushButton { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-weight: bold; font-size: 14px; padding: 0; } QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }")
        btn_x.clicked.connect(self.accept)
        hdr.addWidget(btn_x)
        layout.addLayout(hdr)
        
        # ── Add new driver form ──
        add_box = QFrame(self)
        add_box.setStyleSheet("QFrame { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; }")
        add_layout = QVBoxLayout(add_box)
        add_layout.setContentsMargins(14, 12, 14, 12)
        add_layout.setSpacing(8)
        
        add_lbl = QLabel("➕  تسجيل طيار جديد", add_box)
        add_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #111827; border: none; background: transparent;")
        add_layout.addWidget(add_lbl)
        
        fields_row = QHBoxLayout()
        fields_row.setSpacing(8)
        self.driver_name_input = QLineEdit(add_box)
        self.driver_name_input.setPlaceholderText("اسم الطيار...")
        self.driver_name_input.setFixedHeight(36)
        self.driver_name_input.setStyleSheet("QLineEdit { background: #ffffff; border: 1px solid #d1d5db; border-radius: 6px; color: #111827; padding: 6px 12px; } QLineEdit:focus { border-color: #0078d4; }")
        
        self.driver_phone_input = QLineEdit(add_box)
        self.driver_phone_input.setPlaceholderText("رقم الموبايل...")
        self.driver_phone_input.setMaxLength(11)
        self.driver_phone_input.setFixedHeight(36)
        self.driver_phone_input.setStyleSheet("QLineEdit { background: #ffffff; border: 1px solid #d1d5db; border-radius: 6px; color: #111827; padding: 6px 12px; } QLineEdit:focus { border-color: #0078d4; }")
        
        btn_reg = QPushButton("تسجيل", add_box)
        btn_reg.setFixedHeight(36)
        btn_reg.setFixedWidth(80)
        btn_reg.setStyleSheet("QPushButton { background: #0078d4; color: white; border: none; border-radius: 6px; font-weight: bold; } QPushButton:hover { background: #106ebe; }")
        btn_reg.clicked.connect(self.register_driver)
        
        fields_row.addWidget(self.driver_name_input, stretch=2)
        fields_row.addWidget(self.driver_phone_input, stretch=2)
        fields_row.addWidget(btn_reg)
        add_layout.addLayout(fields_row)
        layout.addWidget(add_box)
        
        # ── Drivers list label ──
        list_lbl = QLabel("قائمة الطيارين المسجلين:", self)
        list_lbl.setStyleSheet("font-weight: bold; color: #616161; font-size: 12px; border: none;")
        layout.addWidget(list_lbl)
        
        # ── Scrollable driver cards area ──
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.drivers_container = QWidget()
        self.drivers_container.setStyleSheet("background: transparent;")
        self.drivers_layout = QVBoxLayout(self.drivers_container)
        self.drivers_layout.setContentsMargins(0, 0, 4, 0)
        self.drivers_layout.setSpacing(8)
        self.scroll.setWidget(self.drivers_container)
        layout.addWidget(self.scroll)

    def load_drivers(self):
        # Clear old cards
        while self.drivers_layout.count():
            child = self.drivers_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, phone, is_active, unsettled_cash FROM drivers ORDER BY is_active DESC, id ASC")
        drivers = c.fetchall()
        
        if not drivers:
            empty_lbl = QLabel("لا يوجد طيارين مسجلين بعد.", self.drivers_container)
            empty_lbl.setStyleSheet("color: #616161; font-size: 13px; border: none; background: transparent; padding: 20px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drivers_layout.addWidget(empty_lbl)
        else:
            for d_id, name, phone, active, unsettled in drivers:
                c.execute("SELECT COUNT(*) FROM orders WHERE driver_id=? AND status='DISPATCHED'", (d_id,))
                load_count = c.fetchone()[0]
                self._build_driver_card(d_id, name, phone, active, load_count, unsettled)
        
        conn.close()
        self.drivers_layout.addStretch()
 
    def _build_driver_card(self, d_id, name, phone, active, load_count, unsettled_cash):
        is_active = bool(active)
        card = QFrame(self.drivers_container)
        
        # Color dot according to status:
        # Green = active & available, Orange = active & out on delivery, Gray = inactive
        if not is_active:
            status_color = "#94a3b8" # Gray
            status_text = "معطل"
            card.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }")
        elif load_count > 0:
            status_color = "#ea580c" # Orange
            status_text = f"بالخارج ({load_count})"
            card.setStyleSheet("QFrame { background: #fff7ed; border: 1px solid #ffedd5; border-radius: 10px; }")
        else:
            status_color = "#16a34a" # Green
            status_text = "متاح"
            card.setStyleSheet("QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; } QFrame:hover { border-color: #0078d4; background: #f8fafc; }")
            
        card.setFixedHeight(84)
        
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(16)
        
        # Status indicator dot
        dot = QLabel("●", card)
        dot.setFixedWidth(12)
        dot.setStyleSheet(f"color: {status_color}; font-size: 16px; border: none; background: transparent;")
        row.addWidget(dot)
        
        # Name + phone
        info = QVBoxLayout()
        info.setSpacing(2)
        info.setContentsMargins(0, 8, 0, 8)
        name_lbl = QLabel(name, card)
        name_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #0f172a; border: none; background: transparent;")
        phone_lbl = QLabel(f"{phone} • {status_text}", card)
        phone_lbl.setStyleSheet("font-size: 11px; color: #64748b; border: none; background: transparent;")
        info.addWidget(name_lbl)
        info.addWidget(phone_lbl)
        row.addLayout(info, stretch=3)
        
        # Unsettled cash
        cash_layout = QVBoxLayout()
        cash_layout.setSpacing(2)
        cash_layout.setContentsMargins(0, 8, 0, 8)
        
        if unsettled_cash > 0:
            cash_lbl = QLabel(f"عهدة: {unsettled_cash:,.1f} ج", card)
            cash_lbl.setStyleSheet("color: #ea580c; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        elif unsettled_cash < 0:
            cash_lbl = QLabel(f"له: {abs(unsettled_cash):,.1f} ج", card)
            cash_lbl.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        else:
            cash_lbl = QLabel("العهدة: 0 ج", card)
            cash_lbl.setStyleSheet("color: #64748b; font-size: 12px; border: none; background: transparent;")
            
        cash_layout.addWidget(cash_lbl)
        row.addLayout(cash_layout, stretch=2)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        
        # Settle button (only if unsettled_cash != 0 or has active dispatched orders)
        if unsettled_cash != 0 or load_count > 0:
            btn_settle = QPushButton("تسوية", card)
            btn_settle.setFixedSize(64, 32)
            btn_settle.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_settle.setStyleSheet("""
                QPushButton {
                    background-color: #0ea5e9; color: white;
                    border: none; border-radius: 6px;
                    font-weight: bold; font-size: 12px;
                }
                QPushButton:hover { background-color: #0284c7; }
                QPushButton:pressed { background-color: #0369a1; }
            """)
            btn_settle.clicked.connect(lambda checked, did=d_id, n=name, cash=unsettled_cash: self.settle_driver_cash(did, n, cash))
            btn_layout.addWidget(btn_settle)
            
        # Toggle button
        btn_toggle = QPushButton("تعطيل" if is_active else "تفعيل", card)
        btn_toggle.setFixedSize(64, 32)
        btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_active:
            btn_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff; color: #475569;
                    border: 1px solid #cbd5e1; border-radius: 6px;
                    font-weight: bold; font-size: 12px;
                }
                QPushButton:hover { background-color: #fee2e2; color: #ef4444; border-color: #fca5a5; }
            """)
        else:
            btn_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff; color: #475569;
                    border: 1px solid #cbd5e1; border-radius: 6px;
                    font-weight: bold; font-size: 12px;
                }
                QPushButton:hover { background-color: #f0fdf4; color: #16a34a; border-color: #bbf7d0; }
            """)
        btn_toggle.clicked.connect(lambda checked, did=d_id, act=is_active: self.toggle_driver(did, act))
        btn_layout.addWidget(btn_toggle)
        
        # Delete button
        btn_del = QPushButton("🗑", card)
        btn_del.setFixedSize(36, 32)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2; color: #b91c1c;
                border: 1px solid #fca5a5; border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #b91c1c; color: white; }
        """)
        btn_del.clicked.connect(lambda checked, did=d_id, n=name: self.delete_driver(did, n))
        btn_layout.addWidget(btn_del)
        
        row.addLayout(btn_layout)
        self.drivers_layout.addWidget(card)

    def settle_driver_cash(self, driver_id, name, unsettled_cash):
        dlg = DriverSettlementDetailDialog(driver_id, name, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_drivers()
            # Also notify parent dashboard if possible to refresh UI
            if self.parent() and hasattr(self.parent(), 'ensure_active_shift'):
                self.parent().ensure_active_shift()
                self.parent().load_pending_delivery_orders()
                if hasattr(self.parent(), "online_sync"):
                    self.parent().online_sync.poll()

    def toggle_driver(self, driver_id, currently_active):
        new_state = 0 if currently_active else 1
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE drivers SET is_active=? WHERE id=?", (new_state, driver_id))
        conn.commit()
        conn.close()
        self.load_drivers()

    def delete_driver(self, driver_id, name):
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"هل أنت متأكد من حذف الطيار «{name}»؟\nلن يمكن التراجع عن هذا الإجراء.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM drivers WHERE id=?", (driver_id,))
            conn.commit()
            conn.close()
            self.load_drivers()

    def register_driver(self):
        name = self.driver_name_input.text().strip()
        phone = self.driver_phone_input.text().strip()
        
        if not name or not phone:
            QMessageBox.warning(self, "بيانات ناقصة", "يرجى ملء اسم الطيار ورقم موبايله.")
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO drivers (name, phone) VALUES (?, ?)", (name, phone))
            conn.commit()
            self.driver_name_input.clear()
            self.driver_phone_input.clear()
            self.load_drivers()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء التسجيل:\n{str(e)}")
        finally:
            conn.close()


class DriverSettlementDetailDialog(QDialog):
    def __init__(self, driver_id, driver_name, parent=None):
        super().__init__(parent)
        self.driver_id = driver_id
        self.driver_name = driver_name
        self.orders = []
        self.checkboxes = {}
        self.init_ui()
        self.load_dispatched_orders()

    def init_ui(self):
        self.setWindowTitle(f"تفاصيل تسوية الطيار: {self.driver_name}")
        self.setMinimumSize(820, 520)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(20, 20, 20, 20)
        self.layout().setSpacing(14)

        # Title
        title_lbl = QLabel(f"الطلبيات الجارية مع الطيار: {self.driver_name}", self)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #0f172a;")
        self.layout().addWidget(title_lbl)

        # Description
        desc_lbl = QLabel("حدد الطلبيات التي تم تسليمها بنجاح للعملاء. الطلبيات غير المحددة ستُعاد تلقائياً كطلبات معلقة في قائمة التكليف.", self)
        desc_lbl.setStyleSheet("font-size: 12px; color: #475569;")
        desc_lbl.setWordWrap(True)
        self.layout().addWidget(desc_lbl)

        # Table for orders
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["حالة التسليم", "رقم الطلب", "العميل", "طريقة الدفع", "العنوان", "الإجمالي"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        
        # Specific column sizes for perfect fit
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 100) # Delivery status check
        self.table.setColumnWidth(1, 85)  # Order number
        self.table.setColumnWidth(2, 130) # Customer name
        self.table.setColumnWidth(3, 100) # Payment method
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) # Stretch Address
        self.table.setColumnWidth(5, 100) # Total
        
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #0f172a;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #cbd5e1;
                padding: 6px;
            }
        """)
        self.layout().addWidget(self.table)

        # Totals layout
        self.totals_lbl = QLabel("إجمالي الكاش المطلوب تحصيله: 0.00 ج.م", self)
        self.totals_lbl.setStyleSheet("font-weight: bold; font-size: 15px; color: #16a34a;")
        self.totals_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.layout().addWidget(self.totals_lbl)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_cancel = QPushButton("تراجع", self)
        btn_cancel.setFixedSize(100, 36)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; color: #475569;
                border: 1px solid #cbd5e1; border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_confirm = QPushButton("تأكيد التسوية والتحصيل", self)
        self.btn_confirm.setFixedSize(180, 36)
        self.btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #16a34a; color: white;
                border: none; border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #15803d; }
        """)
        self.btn_confirm.clicked.connect(self.confirm_settlement)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        self.layout().addLayout(btn_layout)

    def load_dispatched_orders(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT unsettled_cash FROM drivers WHERE id=?", (self.driver_id,))
        row_cash = c.fetchone()
        self.driver_unsettled_cash = row_cash[0] if row_cash else 0.0

        c.execute("""
            SELECT o.id, o.total, o.payment_method, COALESCE(cust.name, 'عميل'),
                   COALESCE(cust.address, '')
            FROM orders o
            LEFT JOIN customers cust ON o.customer_id = cust.id
            WHERE o.driver_id=? AND o.status='DISPATCHED'
            ORDER BY o.id ASC
        """, (self.driver_id,))
        self.orders = c.fetchall()
        conn.close()

        self.table.setRowCount(len(self.orders))
        self.checkboxes.clear()

        if not self.orders:
            # Show empty state message
            self.table.setVisible(False)
            self.empty_lbl = QLabel(self)
            if self.driver_unsettled_cash != 0:
                self.empty_lbl.setText(f"لا توجد طلبيات جارية حالياً.\nولكن توجد عهدة سابقة مسجلة بقيمة: {self.driver_unsettled_cash:,.2f} ج.م")
                self.empty_lbl.setStyleSheet("color: #ea580c; font-weight: bold; font-size: 14px; padding: 20px;")
            else:
                self.empty_lbl.setText("لا توجد طلبيات جارية أو عهد مستحقة على هذا الطيار.")
                self.empty_lbl.setStyleSheet("color: #64748b; font-size: 14px; padding: 20px;")
            self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout().insertWidget(2, self.empty_lbl)
        else:
            self.table.setVisible(True)
            for idx, (o_id, total, pay_method, cust_name, address) in enumerate(self.orders):
                cb = QCheckBox(self)
                cb.setChecked(True)
                cb.setStyleSheet("margin-left: 10px;")
                cb.stateChanged.connect(self.update_totals)
                self.checkboxes[o_id] = cb
                
                cell_widget = QWidget()
                cell_lyt = QHBoxLayout(cell_widget)
                cell_lyt.addWidget(cb)
                cell_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_lyt.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(idx, 0, cell_widget)
                
                self.table.setItem(idx, 1, QTableWidgetItem(f"#{o_id}"))
                self.table.setItem(idx, 2, QTableWidgetItem(cust_name))
                
                pay_txt = "نقدي كاش" if pay_method == "CASH" else ("فيزا كارت" if pay_method == "VISA" else "محفظة ذكية")
                self.table.setItem(idx, 3, QTableWidgetItem(pay_txt))
                self.table.setItem(idx, 4, QTableWidgetItem(address))
                self.table.setItem(idx, 5, QTableWidgetItem(f"{total:,.2f} ج.م"))

        self.update_totals()

    def update_totals(self):
        if not self.orders:
            total_cash = self.driver_unsettled_cash
        else:
            total_cash = 0.0
            for o_id, total, pay_method, _, _ in self.orders:
                cb = self.checkboxes.get(o_id)
                if cb and cb.isChecked() and pay_method == "CASH":
                    total_cash += total
                    
        self.totals_lbl.setText(f"إجمالي الكاش المطلوب تحصيله: {total_cash:,.2f} ج.م")
        
        if len(self.orders) == 0 and self.driver_unsettled_cash == 0:
            self.btn_confirm.setEnabled(False)
        else:
            self.btn_confirm.setEnabled(True)

    def confirm_settlement(self):
        conn = database.get_connection()
        c = conn.cursor()
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("SELECT id FROM shifts WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1")
        shift_row = c.fetchone()
        active_shift_id = shift_row[0] if shift_row else None
        
        if self.orders:
            for o_id, total, pay_method, _, _ in self.orders:
                cb = self.checkboxes.get(o_id)
                if cb and cb.isChecked():
                    c.execute(
                        "UPDATE orders SET status='COMPLETED', closed_at=?, "
                        "online_status=CASE WHEN source='ONLINE' THEN 'COMPLETED' ELSE online_status END "
                        "WHERE id=?",
                        (now_str, o_id),
                    )
                else:
                    c.execute(
                        "UPDATE orders SET status='PENDING', driver_id=NULL, closed_at=NULL, "
                        "online_status=CASE WHEN source='ONLINE' THEN 'PREPARING' ELSE online_status END "
                        "WHERE id=?",
                        (o_id,),
                    )
                reconcile_order_finance(
                    conn, o_id, fallback_shift_id=active_shift_id
                )
        else:
            # A legacy balance with no matching open order is settled explicitly.
            if self.driver_unsettled_cash and active_shift_id:
                c.execute(
                    "UPDATE shifts SET expected_cash=MAX(0.0, expected_cash+?) WHERE id=?",
                    (self.driver_unsettled_cash, active_shift_id),
                )
                c.execute(
                    "UPDATE drivers SET unsettled_cash=0 WHERE id=?", (self.driver_id,)
                )

        conn.commit()
        conn.close()
        self.accept()
