# -*- coding: utf-8 -*-
"""Broost POS - Shift Management Dialogs (Closing & Summary Report)"""
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QMessageBox, QLineEdit, QTextEdit,
    QApplication
)
import database
from styles import STYLE_SHEET
from core import config
from core.printing import print_text_to_printer


class ShiftClosingDialog(QDialog):
    """Cash Register Shift closing report verification with premium, luxurious design."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إغلاق الوردية والدرج")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        
        # Detect screen resolution for adaptive sizing
        screen = QApplication.primaryScreen()
        screen_h = screen.size().height() if screen else 1080
        self.is_small_screen = screen_h <= 768
        
        if self.is_small_screen:
            self.setFixedSize(460, 660)
        else:
            self.setFixedSize(480, 720)
        self.setStyleSheet(STYLE_SHEET)
        
        self.shift_closed = False
        self.expected_cash = 0.0
        
        self.init_ui()
        self.calculate_shift_summary()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        
        # Header block
        header = QHBoxLayout()
        title = QLabel("🔑  إغلاق الوردية والدرج المالي", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4; border: none; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(26, 26)
        btn_close.setStyleSheet("QPushButton { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0; } QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }")
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        layout.addLayout(header)
        
        # LCD Expected Cash Box
        exp_box = QFrame(self)
        exp_box.setObjectName("ExpBox")
        exp_box.setStyleSheet("""
            QFrame#ExpBox {
                background: #f0fdf4;
                border: 1.5px solid #bbf7d0;
                border-radius: 8px;
            }
        """)
        exp_lyt = QVBoxLayout(exp_box)
        exp_lyt.setContentsMargins(12, 8, 12, 8)
        exp_lyt.setSpacing(2)
        exp_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_e = QLabel("💵  الكاش المتوقع وجوده في الدرج", exp_box)
        lbl_e.setStyleSheet("color: #15803d; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        lbl_e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exp_lyt.addWidget(lbl_e)
        
        self.val_exp_cash = QLabel("0.00 ج.م", exp_box)
        self.val_exp_cash.setStyleSheet("font-size: 26px; font-weight: bold; color: #166534; border: none; background: transparent;")
        self.val_exp_cash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exp_lyt.addWidget(self.val_exp_cash)
        layout.addWidget(exp_box)
        
        # Summary Box
        self.summary_box = QFrame(self)
        self.summary_box.setObjectName("SummaryBox")
        self.summary_box.setStyleSheet("""
            QFrame#SummaryBox {
                background: #f9fafb; 
                border: 1px solid #e5e7eb; 
                border-radius: 8px;
            }
        """)
        self.summary_lyt = QVBoxLayout(self.summary_box)
        self.summary_lyt.setSpacing(4)
        self.summary_lyt.setContentsMargins(12, 8, 12, 8)
        
        # Summary Box Title
        lbl_summary_title = QLabel("📊 ملخص مبيعات وردية العمل الحالية", self.summary_box)
        lbl_summary_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #4b5563; border: none; background: transparent; padding-bottom: 2px;")
        self.summary_lyt.addWidget(lbl_summary_title)
        
        layout.addWidget(self.summary_box)
        
        # Input Actual Money Block
        input_container = QFrame(self)
        input_container.setStyleSheet("border: none; background: transparent;")
        input_lyt = QVBoxLayout(input_container)
        input_lyt.setContentsMargins(0, 2, 0, 0)
        input_lyt.setSpacing(6)
        
        lbl_act = QLabel("🔍 اكتب المبلغ الفعلي المتواجد بالدرج حالياً للتحقق والاستلام:", input_container)
        lbl_act.setStyleSheet("color: #374151; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        lbl_act.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        input_lyt.addWidget(lbl_act)
        
        self.actual_input = QLineEdit(input_container)
        self.actual_input.setPlaceholderText("أدخل المبلغ الفعلي...")
        self.actual_input.setFixedHeight(42)
        self.actual_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actual_input.setStyleSheet("""
            QLineEdit {
                font-size: 20px; 
                font-weight: bold; 
                background: #ffffff; 
                border: 1.5px solid #d1d5db; 
                border-radius: 6px; 
                color: #111827; 
                padding: 4px;
            } 
            QLineEdit:focus { 
                border: 1.5px solid #0078d4; 
            }
        """)
        input_lyt.addWidget(self.actual_input)
        layout.addWidget(input_container)
        
        # ── TOUCH NUMERIC KEYPAD ──
        keypad_widget = QWidget(self)
        keypad_layout = QGridLayout(keypad_widget)
        keypad_layout.setSpacing(6)
        keypad_layout.setContentsMargins(0, 4, 0, 0)
        
        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح', 3, 0), ('0', 3, 1), ('.', 3, 2)
        ]
        
        btn_h = 46 if self.is_small_screen else 52
        for text, row, col in keys:
            btn = QPushButton(text, self)
            btn.setFixedHeight(btn_h)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 18px; font-weight: bold; background: #ffffff;
                    border: 1px solid #d1d5db; color: #1a1a1a; border-radius: 8px;
                }
                QPushButton:hover { background: #f3f4f6; }
                QPushButton:pressed { background: #e5e7eb; }
            """)
            
            if text == 'مسح':
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 14px; font-weight: bold; background: #fff4ce;
                        color: #8a6600; border: 1px solid #fde79a; border-radius: 8px;
                    }
                    QPushButton:hover { background: #8a6600; color: white; }
                    QPushButton:pressed { background: #6b5000; color: white; }
                """)
                btn.clicked.connect(self.clear_keypad)
            elif text == '.':
                btn.clicked.connect(lambda checked, t=text: self.press_keypad(t))
            else:
                btn.clicked.connect(lambda checked, t=text: self.press_keypad(t))
                
            keypad_layout.addWidget(btn, row, col)
            
        layout.addWidget(keypad_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        
        btn_cancel = QPushButton("تراجع وإلغاء", self)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #374151;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #f9fafb;
                color: #111827;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_confirm = QPushButton("🔒 تأكيد قفل الوردية والدرج", self)
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #106ebe;
            }
        """)
        self.btn_confirm.clicked.connect(self.close_shift)
        
        btn_layout.addWidget(btn_cancel, stretch=1)
        btn_layout.addWidget(self.btn_confirm, stretch=2)
        layout.addLayout(btn_layout)

    def press_keypad(self, char):
        """Append a digit or decimal to the actual cash input."""
        current = self.actual_input.text()
        if char == '.' and '.' in current:
            return  # Only one decimal point allowed
        self.actual_input.setText(current + char)
        
    def clear_keypad(self):
        """Clear the actual cash input field."""
        self.actual_input.clear()

    def calculate_shift_summary(self):
        if not config.ACTIVE_SHIFT_ID:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        
        # Calculate sums of cashier/delivery orders in this shift
        c.execute("""
            SELECT payment_method, SUM(total - COALESCE(delivery_fee, 0))
            FROM orders
            WHERE shift_id=? AND status='COMPLETED'
            GROUP BY payment_method
        """, (config.ACTIVE_SHIFT_ID,))
        sales_by_pay = dict(c.fetchall())
        
        cash_sales = sales_by_pay.get("CASH", 0.0)
        visa_sales = sales_by_pay.get("VISA", 0.0)
        wallet_sales = sales_by_pay.get("WALLET", 0.0)
        total_sales = cash_sales + visa_sales + wallet_sales
        
        self.expected_cash = cash_sales
        self.val_exp_cash.setText(f"{self.expected_cash:,.2f} ج.م")
        
        # Build premium custom rows
        self.add_summary_row("💵  مدفوعات كاش نقدي", f"{cash_sales:,.2f} ج.م", "#107c10")
        self.add_summary_row("💳  مدفوعات فيزا وكروت", f"{visa_sales:,.2f} ج.م", "#0078d4")
        self.add_summary_row("📱  محفظة إلكترونية", f"{wallet_sales:,.2f} ج.م", "#7c3aed")
        
        # Separator line
        sep = QFrame(self.summary_box)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #e5e7eb; max-height: 1px; border: none;")
        self.summary_lyt.addWidget(sep)
        
        self.add_summary_row("📊  إجمالي مبيعات الوردية", f"{total_sales:,.2f} ج.م", "#0078d4", is_bold=True)
        
        conn.close()
        
    def add_summary_row(self, label_txt, val_txt, val_color, is_bold=False):
        row = QFrame(self.summary_box)
        row.setStyleSheet("background: transparent; border: none;")
        row_lyt = QHBoxLayout(row)
        row_lyt.setContentsMargins(0, 0, 0, 0)
        
        lbl = QLabel(label_txt, row)
        font_sz = "12px" if is_bold else "11px"
        font_w = "bold" if is_bold else "normal"
        lbl.setStyleSheet(f"color: #4b5563; font-size: {font_sz}; font-weight: {font_w}; border: none; background: transparent;")
        row_lyt.addWidget(lbl)
        
        row_lyt.addStretch()
        
        val = QLabel(val_txt, row)
        val_sz = "13px" if is_bold else "12px"
        val.setStyleSheet(f"color: {val_color}; font-size: {val_sz}; font-weight: bold; border: none; background: transparent;")
        row_lyt.addWidget(val)
        
        self.summary_lyt.addWidget(row)

    def close_shift(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE shift_id=? AND status IN ('PENDING', 'DISPATCHED')
        """, (config.ACTIVE_SHIFT_ID,))
        open_orders_count = c.fetchone()[0]
        conn.close()
        if open_orders_count:
            QMessageBox.warning(
                self,
                "لا يمكن إغلاق الوردية",
                f"أنهِ كل الأوردرات المتعلقة بالوردية أولاً. يوجد {open_orders_count} أوردر مفتوح.",
            )
            return

        actual_cash_str = self.actual_input.text().strip()
        if not actual_cash_str:
            QMessageBox.warning(self, "بيانات ناقصة", "يرجى كتابة المبلغ الفعلي المتواجد بالدرج حالياً للتحقق وقفل الشيفت.")
            return
            
        try:
            actual_cash = float(actual_cash_str)
        except ValueError:
            QMessageBox.warning(self, "خطأ في الإدخال", "يرجى إدخال مبلغ مالي صحيح بالدرج.")
            return
            
        diff = actual_cash - self.expected_cash
        if abs(diff) > 0.01:
            status_word = "زيادة بالدرج" if diff > 0 else "عجز بالدرج"
            msg = f"يوجد {status_word} بقيمة {abs(diff):,.2f} ج.م.\nهل ترغب في قفل الوردية وترحيل هذا الفارق المالي للمدير؟"
            res = QMessageBox.warning(self, "تنبيه فارق مالي", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res != QMessageBox.StandardButton.Yes:
                return
                
        # Update shift in DB
        conn = database.get_connection()
        c = conn.cursor()
        
        c.execute("""
            UPDATE shifts
            SET closed_at = ?,
                actual_cash = ?,
                cash_sales = (SELECT COALESCE(SUM(total - COALESCE(delivery_fee, 0)), 0) FROM orders WHERE shift_id=? AND status='COMPLETED' AND payment_method='CASH'),
                visa_sales = (SELECT COALESCE(SUM(total - COALESCE(delivery_fee, 0)), 0) FROM orders WHERE shift_id=? AND status='COMPLETED' AND payment_method='VISA'),
                wallet_sales = (SELECT COALESCE(SUM(total - COALESCE(delivery_fee, 0)), 0) FROM orders WHERE shift_id=? AND status='COMPLETED' AND payment_method='WALLET'),
                total_sales = (SELECT COALESCE(SUM(total - COALESCE(delivery_fee, 0)), 0) FROM orders WHERE shift_id=? AND status='COMPLETED')
            WHERE id = ?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), actual_cash, config.ACTIVE_SHIFT_ID, config.ACTIVE_SHIFT_ID, config.ACTIVE_SHIFT_ID, config.ACTIVE_SHIFT_ID, config.ACTIVE_SHIFT_ID))
        
        conn.commit()
        conn.close()
        
        self.closed_shift_id = config.ACTIVE_SHIFT_ID
        config.ACTIVE_SHIFT_ID = None
        self.shift_closed = True
        self.accept()


class ShiftSummaryReportDialog(QDialog):
    """Displays a beautiful, premium shift summary report after closing the shift with printing options."""
    def __init__(self, shift_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تقرير نهاية الوردية")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(500, 600)
        self.setStyleSheet(STYLE_SHEET)
        
        self.shift_id = shift_id
        self.shift_data = {}
        self.orders_count = 0
        self.deleted_count = 0
        
        self.load_shift_data()
        self.init_ui()
        
    def load_shift_data(self):
        conn = database.get_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT id, opened_at, closed_at, expected_cash, actual_cash, 
                   cash_sales, visa_sales, wallet_sales, total_sales
            FROM shifts WHERE id = ?
        """, (self.shift_id,))
        row = c.fetchone()
        
        if row:
            self.shift_data = {
                "id": row[0],
                "opened_at": row[1],
                "closed_at": row[2],
                "expected_cash": row[3],
                "actual_cash": row[4],
                "cash_sales": row[5],
                "visa_sales": row[6],
                "wallet_sales": row[7],
                "total_sales": row[8]
            }
            
        c.execute("SELECT COUNT(id) FROM orders WHERE shift_id=? AND status='COMPLETED'", (self.shift_id,))
        self.orders_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(id) FROM orders WHERE shift_id=? AND status='DELETED'", (self.shift_id,))
        self.deleted_count = c.fetchone()[0]
        
        conn.close()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Header block
        header = QHBoxLayout()
        title = QLabel("📄 تقرير إغلاق الوردية والدرج", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4; border: none; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(26, 26)
        btn_close.setStyleSheet("QPushButton { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0; } QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }")
        btn_close.clicked.connect(self.accept)
        header.addWidget(btn_close)
        layout.addLayout(header)
        
        # Report Scroll/Text Area for invoice look
        self.report_text = QTextEdit(self)
        self.report_text.setReadOnly(True)
        self.report_text.setStyleSheet("""
            QTextEdit {
                background: white; 
                color: black; 
                font-family: 'Courier New', monospace; 
                font-size: 12px;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        
        # Generate the plain text Arabic report
        report_content = self.generate_report_string()
        self.report_text.setText(report_content)
        layout.addWidget(self.report_text)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_print = QPushButton("🖨️ طباعة التقرير", self)
        btn_print.setFixedHeight(40)
        btn_print.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #106ebe;
            }
        """)
        btn_print.clicked.connect(self.print_report)
        
        btn_done = QPushButton("🚪 خروج وتسجيل الخروج", self)
        btn_done.setFixedHeight(40)
        btn_done.setObjectName("BtnDark")
        btn_done.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_done, stretch=1)
        btn_layout.addWidget(btn_print, stretch=2)
        layout.addLayout(btn_layout)
        
    def generate_report_string(self):
        sd = self.shift_data
        if not sd:
            return "تعذر تحميل بيانات الوردية."
            
        diff = sd["actual_cash"] - sd["expected_cash"]
        status = "مطابق"
        if diff > 0.01:
            status = "زيادة بالدرج"
        elif diff < -0.01:
            status = "عجز بالدرج"
            
        lines = []
        lines.append("========================================")
        lines.append("             تقرير إغلاق الوردية  ")
        lines.append("========================================")
        lines.append(f"رقم الوردية: {sd['id']}")
        lines.append(f"تاريخ الفتح: {sd['opened_at']}")
        lines.append(f"تاريخ القفل: {sd['closed_at']}")
        lines.append("========================================")
        lines.append("الملخص المالي للمبيعات:")
        lines.append(f"- مبيعات الكاش النقدي : {sd['cash_sales']:,.2f} ج.م")
        lines.append(f"- مبيعات فيزا كارت     : {sd['visa_sales']:,.2f} ج.م")
        lines.append(f"- مبيعات محفظة إلكترونية: {sd['wallet_sales']:,.2f} ج.م")
        lines.append("----------------------------------------")
        lines.append(f"إجمالي مبيعات الوردية  : {sd['total_sales']:,.2f} ج.م")
        lines.append("========================================")
        lines.append("تسوية وجرد صندوق الدرج:")
        lines.append(f"- الكاش المتوقع بالدرج: {sd['expected_cash']:,.2f} ج.م")
        lines.append(f"- الكاش الفعلي المدخل  : {sd['actual_cash']:,.2f} ج.م")
        lines.append("----------------------------------------")
        lines.append(f"الفارق المالي         : {abs(diff):,.2f} ج.م")
        lines.append(f"حالة التسوية         : {status}")
        lines.append("========================================")
        lines.append("إحصائيات وحركة الطلبات:")
        lines.append(f"- إجمالي الفواتير المكتملة: {self.orders_count}")
        lines.append(f"- إجمالي الفواتير المحذوفة: {self.deleted_count}")
        lines.append("========================================")
        lines.append("           شكراً لعملكم الدؤوب!         ")
        lines.append("         تم إغلاق الوردية بنجاح.         ")
        lines.append("========================================")
        
        return "\n".join(lines)
        
    def print_report(self):
        if not config.PRINTER_ONLINE:
            QMessageBox.critical(self, "خطأ بالطابعة", "تنبيه: تعذر إرسال الأمر! طابعة الفواتير غير متصلة أو انقطع اتصال الكابل.")
            return
            
        success = print_text_to_printer(self.generate_report_string(), self)
        if success:
            QMessageBox.information(self, "طابعة النظام", "تم طباعة تقرير الوردية بنجاح.")

