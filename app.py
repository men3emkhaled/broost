# -*- coding: utf-8 -*-
import sys
import os
import json
import sqlite3
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QPoint
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QLineEdit, QTextEdit,
    QScrollArea, QFrame, QDialog, QComboBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QStackedWidget, QTabWidget
)
from PyQt6.QtGui import QIcon, QFont, QMouseEvent
from PyQt6.QtPrintSupport import QPrinter

import database
from styles import STYLE_SHEET

# Global configuration variables
ACTIVE_SHIFT_ID = None
CURRENT_USER_AUTHENTICATED = False
PRINTER_ONLINE = True

class CustomTitleBar(QWidget):
    """Custom titlebar for the frameless PyQt application window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("TitleBar")
        self.setFixedHeight(38)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        # Window controls (Close, Maximize, Minimize) on left for RTL Arabic
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setSpacing(2)
        
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setObjectName("WindowControlBtn")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.setStyleSheet("QPushButton { background: transparent; border: none; color: #ff8e8e; font-weight: bold; } QPushButton:hover { background: #ef4444; color: white; }")
        self.btn_close.clicked.connect(self.close_window)
        
        self.btn_maximize = QPushButton("▢", self)
        self.btn_maximize.setObjectName("WindowControlBtn")
        self.btn_maximize.setFixedSize(30, 26)
        self.btn_maximize.setStyleSheet("QPushButton { background: transparent; border: none; color: #ccc; } QPushButton:hover { background: rgba(255,255,255,0.08); }")
        self.btn_maximize.clicked.connect(self.maximize_window)
        
        self.btn_minimize = QPushButton("—", self)
        self.btn_minimize.setObjectName("WindowControlBtn")
        self.btn_minimize.setFixedSize(30, 26)
        self.btn_minimize.setStyleSheet("QPushButton { background: transparent; border: none; color: #ccc; } QPushButton:hover { background: rgba(255,255,255,0.08); }")
        self.btn_minimize.clicked.connect(self.minimize_window)
        
        self.controls_layout.addWidget(self.btn_close)
        self.controls_layout.addWidget(self.btn_maximize)
        self.controls_layout.addWidget(self.btn_minimize)
        
        layout.addLayout(self.controls_layout)
        layout.addStretch()
        
        # App Title on right (Arabic RTL)
        self.title_label = QLabel("بروستر سيستم - نظام مبيعات الكاشير والدليفري v1.0.0", self)
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)
        
        self.drag_position = QPoint()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.parent.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def close_window(self):
        self.parent.close()

    def maximize_window(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def minimize_window(self):
        self.parent.showMinimized()


class LoginDialog(QDialog):
    """Password lock screen at system startup."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تسجيل الدخول للسيستم")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(360, 480)
        self.setStyleSheet(STYLE_SHEET)
        
        self.password_value = ""
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title_label = QLabel("بروستر سيستم\nالرقم السري لفتح النظام", self)
        title_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #8cffa7; background: transparent;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        self.pin_display = QLineEdit(self)
        self.pin_display.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setStyleSheet("font-size: 26px; background: #050a0a; border: 2px solid #263434; padding: 8px; color: #ffffff; border-radius: 6px;")
        self.pin_display.setReadOnly(True)
        layout.addWidget(self.pin_display)
        
        # Touch Keypad Grid
        grid_widget = QWidget(self)
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(6)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح', 3, 0), ('0', 3, 1), ('دخول', 3, 2)
        ]
        
        for text, row, col in keys:
            btn = QPushButton(text, self)
            btn.setFixedSize(80, 56)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 16px; font-weight: bold; background: rgba(255,255,255,0.05); border: 1px solid #263434; color: white; border-radius: 4px;
                }
                QPushButton:hover { background: rgba(255,255,255,0.12); }
            """)
            
            if text == 'دخول':
                btn.setStyleSheet("QPushButton { font-size: 16px; font-weight: bold; background: #8cffa7; color: #0e1e1d; border: 1px solid #263434; border-radius: 4px; } QPushButton:hover { background: #dcffe4; }")
                btn.clicked.connect(self.submit_login)
            elif text == 'مسح':
                btn.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; background: #ffd9a8; color: #0e1e1d; border: 1px solid #263434; border-radius: 4px; } QPushButton:hover { background: #ffe5f9; }")
                btn.clicked.connect(self.clear_keys)
            else:
                btn.clicked.connect(lambda checked, t=text: self.press_key(t))
                
            grid_layout.addWidget(btn, row, col)
            
        layout.addWidget(grid_widget)
        
        # Removed default password label to make the interface look professional and clean.
        
    def press_key(self, char):
        if len(self.password_value) < 6:
            self.password_value += char
            self.pin_display.setText(self.password_value)
            
    def clear_keys(self):
        self.password_value = ""
        self.pin_display.setText("")
        
    def submit_login(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='app_password'")
        stored_password = c.fetchone()[0]
        conn.close()
        
        if self.password_value == stored_password:
            global CURRENT_USER_AUTHENTICATED
            CURRENT_USER_AUTHENTICATED = True
            self.accept()
        else:
            QMessageBox.critical(self, "خطأ بالرقم السري", "الرقم السري الذي أدخلته غير صحيح. أعد المحاولة.")
            self.clear_keys()


class PasswordVerificationDialog(QDialog):
    """Requires the manager password (default 456) to confirm deletion or closing shift."""
    def __init__(self, prompt_text="عملية مسح الطلب", parent=None):
        super().__init__(parent)
        self.setWindowTitle("تأكيد الصلاحية")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(350, 240)
        self.setStyleSheet(STYLE_SHEET)
        
        self.prompt_text = prompt_text
        self.verified = False
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        title = QLabel("تأكيد صلاحية المدير مطلوبة", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffa8f6;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        desc = QLabel(f"إجراء حسّاس: {self.prompt_text}.\nالرجاء إدخال باسوورد المدير للتأكيد:", self)
        desc.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        self.pwd_input = QLineEdit(self)
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pwd_input.setStyleSheet("font-size: 20px; background: #050a0a; border: 1px solid #263434; padding: 8px; color: white; border-radius: 6px;")
        layout.addWidget(self.pwd_input)
        
        # Removed manager default password label to make the interface look professional and clean.
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_confirm = QPushButton("تأكيد الإجراء", self)
        self.btn_confirm.setObjectName("BtnPink")
        self.btn_confirm.clicked.connect(self.verify_password)
        
        btn_cancel = QPushButton("تراجع وإلغاء", self)
        btn_cancel.setObjectName("BtnDark")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_confirm)
        layout.addLayout(btn_layout)
        
    def verify_password(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='delete_password'")
        stored_password = c.fetchone()[0]
        conn.close()
        
        if self.pwd_input.text() == stored_password:
            self.verified = True
            self.accept()
        else:
            QMessageBox.critical(self, "خطأ بالرقم السري", "الرقم السري للمدير غير صحيح.")
            self.pwd_input.clear()


class ItemDetailsPickerDialog(QDialog):
    """Allows selecting sizes, optional extras, and quantity before adding to cart."""
    def __init__(self, item_id, item_name, base_price, parent=None):
        super().__init__(parent)
        self.setWindowTitle("خيارات الصنف")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(420, 480)
        self.setStyleSheet(STYLE_SHEET)
        
        self.item_id = item_id
        self.item_name = item_name
        self.base_price = base_price
        
        self.selected_size = "عادي"
        self.size_offset = 0.0
        self.selected_extras = {} # name -> price
        self.quantity = 1
        
        self.init_ui()
        self.load_options()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        # Item Header Title
        header_label = QLabel(self.item_name, self)
        header_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #8cffa7;")
        layout.addWidget(header_label)
        
        # [1] Sizes section
        sizes_label = QLabel("اختر الحجم أو الطعم:", self)
        sizes_label.setStyleSheet("font-weight: bold; color: #ffd9a8;")
        layout.addWidget(sizes_label)
        
        self.sizes_area = QWidget(self)
        self.sizes_layout = QHBoxLayout(self.sizes_area)
        self.sizes_layout.setContentsMargins(0, 0, 0, 0)
        self.sizes_layout.setSpacing(6)
        layout.addWidget(self.sizes_area)
        
        # [2] Extras section
        extras_label = QLabel("إضافات إضافية (اختياري):", self)
        extras_label.setStyleSheet("font-weight: bold; color: #ffd9a8;")
        layout.addWidget(extras_label)
        
        self.extras_scroll = QScrollArea(self)
        self.extras_scroll.setWidgetResizable(True)
        self.extras_scroll.setStyleSheet("background: transparent; border: 1px solid #263434;")
        self.extras_container = QWidget()
        self.extras_layout = QVBoxLayout(self.extras_container)
        self.extras_layout.setContentsMargins(8, 8, 8, 8)
        self.extras_layout.setSpacing(6)
        self.extras_scroll.setWidget(self.extras_container)
        layout.addWidget(self.extras_scroll)
        
        # [3] Quantity counter row
        qty_row = QHBoxLayout()
        qty_lbl = QLabel("الكمية المطلوبة:", self)
        qty_lbl.setStyleSheet("font-weight: bold;")
        qty_row.addWidget(qty_lbl)
        qty_row.addStretch()
        
        btn_minus = QPushButton("-", self)
        btn_minus.setFixedSize(36, 32)
        btn_minus.clicked.connect(lambda: self.adjust_qty(-1))
        
        self.qty_val_lbl = QLabel("1", self)
        self.qty_val_lbl.setStyleSheet("font-size: 16px; font-weight: bold; min-width: 30px;")
        self.qty_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_plus = QPushButton("+", self)
        btn_plus.setFixedSize(36, 32)
        btn_plus.clicked.connect(lambda: self.adjust_qty(1))
        
        qty_row.addWidget(btn_minus)
        qty_row.addWidget(self.qty_val_lbl)
        qty_row.addWidget(btn_plus)
        layout.addLayout(qty_row)
        
        # Footer Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_add = QPushButton("إضافة إلى السلة", self)
        self.btn_add.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("تراجع", self)
        btn_cancel.setObjectName("BtnDark")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_add)
        layout.addLayout(btn_layout)

    def load_options(self):
        conn = database.get_connection()
        c = conn.cursor()
        
        # Load sizes
        c.execute("SELECT name, price_offset FROM menu_item_sizes WHERE item_id=?", (self.item_id,))
        sizes = c.fetchall()
        
        # Draw size buttons
        self.size_buttons = []
        if sizes:
            for name, offset in sizes:
                btn = QPushButton(f"{name} (+{offset} ج.م)", self)
                btn.setCheckable(True)
                btn.setProperty("name", name)
                btn.setProperty("offset", offset)
                btn.setStyleSheet("QPushButton { background-color: rgba(255,255,255,0.03); border: 1px solid #263434; color: white; } QPushButton:checked { background-color: #8cffa7; color: #0e1e1d; }")
                btn.clicked.connect(lambda checked, b=btn: self.select_size(b))
                
                self.sizes_layout.addWidget(btn)
                self.size_buttons.append(btn)
                
            # Default check first
            self.size_buttons[0].setChecked(True)
            self.selected_size = self.size_buttons[0].property("name")
            self.size_offset = self.size_buttons[0].property("offset")
        else:
            # Standalone default size
            lbl = QLabel("حجم موحد قياسي", self)
            lbl.setStyleSheet("color: rgba(255,255,255,0.5);")
            self.sizes_layout.addWidget(lbl)
            
        # Load extras
        c.execute("SELECT name, price FROM menu_item_extras WHERE item_id=?", (self.item_id,))
        extras = c.fetchall()
        
        self.extra_buttons = []
        if extras:
            for name, price in extras:
                btn = QPushButton(f"{name} (+{price} ج.م)", self)
                btn.setCheckable(True)
                btn.setProperty("name", name)
                btn.setProperty("price", price)
                btn.setStyleSheet("QPushButton { text-align: right; background-color: rgba(255,255,255,0.02); border: 1px solid #263434; color: white; padding-right: 12px; } QPushButton:checked { background-color: #ffd9a8; color: #0e1e1d; border-color: #263434; }")
                btn.clicked.connect(lambda checked, b=btn: self.toggle_extra(b))
                
                self.extras_layout.addWidget(btn)
                self.extra_buttons.append(btn)
            self.extras_layout.addStretch()
        else:
            lbl = QLabel("لا توجد إضافات متاحة لهذا الصنف", self)
            lbl.setStyleSheet("color: rgba(255,255,255,0.4); font-style: italic;")
            self.extras_layout.addWidget(lbl)
            
        conn.close()

    def select_size(self, clicked_btn):
        for btn in self.size_buttons:
            btn.setChecked(btn == clicked_btn)
            
        self.selected_size = clicked_btn.property("name")
        self.size_offset = float(clicked_btn.property("offset"))

    def toggle_extra(self, clicked_btn):
        name = clicked_btn.property("name")
        price = float(clicked_btn.property("price"))
        
        if clicked_btn.isChecked():
            self.selected_extras[name] = price
        else:
            if name in self.selected_extras:
                del self.selected_extras[name]

    def adjust_qty(self, delta):
        new_qty = self.quantity + delta
        if new_qty >= 1:
            self.quantity = new_qty
            self.qty_val_lbl.setText(str(self.quantity))

    def prefill_selections(self, size_name, qty, extras):
        self.quantity = qty
        self.qty_val_lbl.setText(str(qty))
        
        # Select size
        for btn in self.size_buttons:
            if btn.property("name") == size_name:
                btn.setChecked(True)
                self.selected_size = size_name
                self.size_offset = float(btn.property("offset") or 0.0)
            else:
                btn.setChecked(False)
                
        # Select extras
        self.selected_extras = extras.copy()
        for btn in self.extra_buttons:
            name = btn.property("name")
            if name in extras:
                btn.setChecked(True)
            else:
                btn.setChecked(False)


class DriversAdminDialog(QDialog):
    """View and manage driver loads/load balances and registers new delivery captains."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة طياري التوصيل")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(520, 560)
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
        title.setStyleSheet("font-size: 18px; font-weight: 900; color: #a8deff; border: none;")
        hdr.addWidget(title)
        hdr.addStretch()
        btn_x = QPushButton("✕", self)
        btn_x.setFixedSize(32, 32)
        btn_x.setStyleSheet("QPushButton { background: rgba(255,168,246,0.08); color: #ffa8f6; border: 1px solid rgba(255,168,246,0.3); border-radius: 6px; font-weight: bold; font-size: 14px; padding: 0; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; }")
        btn_x.clicked.connect(self.accept)
        hdr.addWidget(btn_x)
        layout.addLayout(hdr)
        
        # ── Add new driver form ──
        add_box = QFrame(self)
        add_box.setStyleSheet("QFrame { background: rgba(168,222,255,0.04); border: 1px solid rgba(168,222,255,0.2); border-radius: 10px; }")
        add_layout = QVBoxLayout(add_box)
        add_layout.setContentsMargins(14, 12, 14, 12)
        add_layout.setSpacing(8)
        
        add_lbl = QLabel("➕  تسجيل طيار جديد", add_box)
        add_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #a8deff; border: none; background: transparent;")
        add_layout.addWidget(add_lbl)
        
        fields_row = QHBoxLayout()
        fields_row.setSpacing(8)
        self.driver_name_input = QLineEdit(add_box)
        self.driver_name_input.setPlaceholderText("اسم الطيار...")
        self.driver_name_input.setFixedHeight(36)
        
        self.driver_phone_input = QLineEdit(add_box)
        self.driver_phone_input.setPlaceholderText("رقم الموبايل...")
        self.driver_phone_input.setMaxLength(11)
        self.driver_phone_input.setFixedHeight(36)
        
        btn_reg = QPushButton("تسجيل", add_box)
        btn_reg.setFixedHeight(36)
        btn_reg.setFixedWidth(80)
        btn_reg.setObjectName("BtnBlue")
        btn_reg.clicked.connect(self.register_driver)
        
        fields_row.addWidget(self.driver_name_input, stretch=2)
        fields_row.addWidget(self.driver_phone_input, stretch=2)
        fields_row.addWidget(btn_reg)
        add_layout.addLayout(fields_row)
        layout.addWidget(add_box)
        
        # ── Drivers list label ──
        list_lbl = QLabel("قائمة الطيارين المسجلين:", self)
        list_lbl.setStyleSheet("font-weight: bold; color: rgba(255,255,255,0.5); font-size: 12px; border: none;")
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
        c.execute("SELECT id, name, phone, is_active FROM drivers ORDER BY is_active DESC, id ASC")
        drivers = c.fetchall()
        
        if not drivers:
            empty_lbl = QLabel("لا يوجد طيارين مسجلين بعد.", self.drivers_container)
            empty_lbl.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 13px; border: none; background: transparent; padding: 20px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drivers_layout.addWidget(empty_lbl)
        else:
            for d_id, name, phone, active in drivers:
                c.execute("SELECT COUNT(*) FROM orders WHERE driver_id=? AND status='DISPATCHED'", (d_id,))
                load_count = c.fetchone()[0]
                self._build_driver_card(d_id, name, phone, active, load_count)
        
        conn.close()
        self.drivers_layout.addStretch()

    def _build_driver_card(self, d_id, name, phone, active, load_count):
        is_active = bool(active)
        card = QFrame(self.drivers_container)
        if is_active:
            card.setStyleSheet("QFrame { background: rgba(255,255,255,0.03); border: 1px solid #263434; border-radius: 10px; } QFrame:hover { border-color: rgba(168,222,255,0.4); background: rgba(168,222,255,0.03); }")
        else:
            card.setStyleSheet("QFrame { background: rgba(255,168,246,0.02); border: 1px solid rgba(255,168,246,0.12); border-radius: 10px; }")
        card.setFixedHeight(68)
        
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 0, 10, 0)
        row.setSpacing(10)
        
        # Colored status indicator dot
        dot = QLabel("●", card)
        dot.setFixedWidth(14)
        dot.setStyleSheet(f"color: {'#8cffa7' if is_active else '#ffa8f6'}; font-size: 18px; border: none; background: transparent;")
        row.addWidget(dot)
        
        # Name + phone stacked
        info = QVBoxLayout()
        info.setSpacing(3)
        name_lbl = QLabel(name, card)
        name_lbl.setStyleSheet("font-weight: 800; font-size: 13px; color: white; border: none; background: transparent;")
        phone_lbl = QLabel(phone, card)
        phone_lbl.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.4); border: none; background: transparent;")
        info.addWidget(name_lbl)
        info.addWidget(phone_lbl)
        row.addLayout(info, stretch=1)
        
        # Active orders badge
        badge_txt = f"🚗 {load_count}" if load_count > 0 else "متاح"
        badge_color = "#a8deff" if load_count > 0 else "rgba(255,255,255,0.25)"
        badge_bg = "rgba(168,222,255,0.08)" if load_count > 0 else "rgba(255,255,255,0.03)"
        load_lbl = QLabel(badge_txt, card)
        load_lbl.setStyleSheet(f"background: {badge_bg}; color: {badge_color}; border: 1px solid {badge_color}; border-radius: 5px; padding: 3px 10px; font-size: 11px; font-weight: bold;")
        row.addWidget(load_lbl)
        
        # Toggle active/inactive button
        btn_toggle = QPushButton("تعطيل" if is_active else "تفعيل", card)
        btn_toggle.setFixedSize(62, 30)
        if is_active:
            btn_toggle.setStyleSheet("QPushButton { background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.5); border: 1px solid #263434; border-radius: 6px; font-weight: bold; font-size: 11px; } QPushButton:hover { background: rgba(255,168,246,0.15); color: #ffa8f6; border-color: rgba(255,168,246,0.4); }")
        else:
            btn_toggle.setStyleSheet("QPushButton { background: rgba(140,255,167,0.08); color: #8cffa7; border: 1px solid rgba(140,255,167,0.3); border-radius: 6px; font-weight: bold; font-size: 11px; } QPushButton:hover { background: #8cffa7; color: #0e1e1d; }")
        btn_toggle.clicked.connect(lambda checked, did=d_id, act=is_active: self.toggle_driver(did, act))
        row.addWidget(btn_toggle)
        
        # Delete button
        btn_del = QPushButton("🗑", card)
        btn_del.setFixedSize(34, 30)
        btn_del.setStyleSheet("QPushButton { background: rgba(255,168,246,0.05); color: #ffa8f6; border: 1px solid rgba(255,168,246,0.2); border-radius: 6px; font-size: 14px; padding: 0; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; }")
        btn_del.clicked.connect(lambda checked, did=d_id, n=name: self.delete_driver(did, n))
        row.addWidget(btn_del)
        
        self.drivers_layout.addWidget(card)

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


class MenuAdminDialog(QDialog):
    """Panel to toggle item stock status or change pricing. Requires password 456 to load."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة المنيو والتسعير")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(580, 500)
        self.setStyleSheet(STYLE_SHEET)
        
        self.init_ui()
        self.load_menu_items()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel("تعديل المنيو والتوفر المؤقت للأصناف", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8cffa7;")
        layout.addWidget(title)
        
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: 1px solid #263434;")
        
        self.container = QWidget()
        self.scroll_layout = QVBoxLayout(self.container)
        self.scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_layout.setSpacing(8)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        
        btn_close = QPushButton("حفظ التغييرات وإغلاق", self)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def load_menu_items(self):
        # Clear scroll area
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, base_price, is_available FROM menu_items")
        items = c.fetchall()
        
        for item_id, name, price, available in items:
            row = QFrame(self.container)
            row.setStyleSheet("background: rgba(255,255,255,0.01); border: 1px solid #263434; border-radius: 6px; padding: 6px;")
            r_layout = QHBoxLayout(row)
            
            lbl_name = QLabel(name, row)
            lbl_name.setStyleSheet("font-weight: bold; font-size: 13px;")
            r_layout.addWidget(lbl_name)
            
            r_layout.addStretch()
            
            # Price input
            lbl_prc = QLabel("السعر الأساسي:", row)
            r_layout.addWidget(lbl_prc)
            
            price_input = QLineEdit(str(price), row)
            price_input.setFixedWidth(70)
            price_input.setProperty("item_id", item_id)
            price_input.textChanged.connect(lambda text, idx=item_id: self.update_price(idx, text))
            r_layout.addWidget(price_input)
            
            # Stock availability button
            btn_stock = QPushButton("متوفر نشط" if available else "غير متوفر (خلصان)", row)
            btn_stock.setProperty("item_id", item_id)
            btn_stock.setProperty("status", available)
            if available:
                btn_stock.setStyleSheet("background-color: #8cffa7; color: #0e1e1d; border-radius: 4px; font-weight: bold;")
            else:
                btn_stock.setStyleSheet("background-color: #ffa8f6; color: #0e1e1d; border-radius: 4px; font-weight: bold;")
                
            btn_stock.clicked.connect(lambda checked, b=btn_stock: self.toggle_availability(b))
            r_layout.addWidget(btn_stock)
            
            self.scroll_layout.addWidget(row)
            
        self.scroll_layout.addStretch()
        conn.close()

    def update_price(self, item_id, price_str):
        try:
            price = float(price_str)
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("UPDATE menu_items SET base_price=? WHERE id=?", (price, item_id))
            conn.commit()
            conn.close()
        except ValueError:
            pass # ignore invalid float edits temporarily

    def toggle_availability(self, btn):
        item_id = btn.property("item_id")
        current_status = btn.property("status")
        new_status = 0 if current_status == 1 else 1
        
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE menu_items SET is_available=? WHERE id=?", (new_status, item_id))
        conn.commit()
        conn.close()
        
        # update button UI
        btn.setProperty("status", new_status)
        if new_status == 1:
            btn.setText("متوفر نشط")
            btn.setStyleSheet("background-color: #8cffa7; color: #0e1e1d; border-radius: 4px; font-weight: bold;")
        else:
            btn.setText("غير متوفر (خلصان)")
            btn.setStyleSheet("background-color: #ffa8f6; color: #0e1e1d; border-radius: 4px; font-weight: bold;")


class ReportsDialog(QDialog):
    """Business Analytics and Graphical Reports Dashboard with detailed order history."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("لوحة تقارير المبيعات")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(980, 620)
        self.setStyleSheet(STYLE_SHEET)
        
        self.filter_range = "day"
        self.init_ui()
        self.load_analytics()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        # ── Header row ──
        header = QHBoxLayout()
        title = QLabel("📊  لوحة المبيعات والتقارير", self)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #a8deff; border: none;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Date Filter buttons
        self.btn_day = QPushButton("اليوم", self)
        self.btn_day.setCheckable(True)
        self.btn_day.setChecked(True)
        self.btn_day.setFixedSize(80, 32)
        self.btn_day.clicked.connect(lambda: self.change_filter("day"))
        
        self.btn_week = QPushButton("7 أيام", self)
        self.btn_week.setCheckable(True)
        self.btn_week.setFixedSize(80, 32)
        self.btn_week.clicked.connect(lambda: self.change_filter("week"))
        
        self.btn_month = QPushButton("30 يوم", self)
        self.btn_month.setCheckable(True)
        self.btn_month.setFixedSize(80, 32)
        self.btn_month.clicked.connect(lambda: self.change_filter("month"))
        
        header.addWidget(self.btn_day)
        header.addWidget(self.btn_week)
        header.addWidget(self.btn_month)
        
        # Close button
        btn_x = QPushButton("✕", self)
        btn_x.setFixedSize(32, 32)
        btn_x.setStyleSheet("QPushButton { background: rgba(255,168,246,0.08); color: #ffa8f6; border: 1px solid rgba(255,168,246,0.3); border-radius: 6px; font-weight: bold; font-size: 14px; padding: 0; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; }")
        btn_x.clicked.connect(self.accept)
        header.addWidget(btn_x)
        
        layout.addLayout(header)
        
        # ── Tab widget ──
        self.tabs = QTabWidget(self)
        
        # ── Tab 1: Overview ──
        tab_overview = QWidget()
        overview_layout = QVBoxLayout(tab_overview)
        overview_layout.setContentsMargins(10, 10, 10, 10)
        overview_layout.setSpacing(14)
        
        # Metrics Grid
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)
        
        self.card_sales = self.create_stat_card("صافي الإيرادات الكلية 💰", "0.00 ج.م", "#8cffa7")
        self.card_orders = self.create_stat_card("عدد فواتير البيع الناجحة 📝", "0", "#ffffff")
        self.card_dish = self.create_stat_card("الأكلة الأكثر طلباً 🏆", "بروست", "#ffd9a8")
        self.card_hour = self.create_stat_card("ساعة ذروة الزحام 🔥", "8:00 مساءً", "#a8deff")
        
        metrics_grid.addWidget(self.card_sales, 0, 0)
        metrics_grid.addWidget(self.card_orders, 0, 1)
        metrics_grid.addWidget(self.card_dish, 0, 2)
        metrics_grid.addWidget(self.card_hour, 0, 3)
        overview_layout.addLayout(metrics_grid)
        
        # Distribution charts and leaderboard row
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(14)
        
        # Channels comparison box
        self.chan_box = QFrame(tab_overview)
        self.chan_box.setStyleSheet("background: rgba(255,255,255,0.01); border: 1px solid #263434; border-radius: 8px; padding: 12px;")
        chan_layout = QVBoxLayout(self.chan_box)
        chan_title = QLabel("قنوات التوزيع المفضلة ومبيعاتها", self.chan_box)
        chan_title.setStyleSheet("font-weight: bold; color: #a8deff; font-size: 13px; border: none; background: transparent;")
        chan_layout.addWidget(chan_title)
        
        self.bars_container = QWidget(self.chan_box)
        self.bars_layout = QVBoxLayout(self.bars_container)
        self.bars_layout.setContentsMargins(0, 8, 0, 0)
        self.bars_layout.setSpacing(12)
        chan_layout.addWidget(self.bars_container)
        charts_layout.addWidget(self.chan_box, stretch=1)
        
        # Drivers leaderboard
        self.lead_box = QFrame(tab_overview)
        self.lead_box.setStyleSheet("background: rgba(255,255,255,0.01); border: 1px solid #263434; border-radius: 8px; padding: 12px;")
        lead_layout = QVBoxLayout(self.lead_box)
        lead_title = QLabel("جدول مبيعات وتكليفات طيارين الدليفري", self.lead_box)
        lead_title.setStyleSheet("font-weight: bold; color: #a8deff; font-size: 13px; border: none; background: transparent;")
        lead_layout.addWidget(lead_title)
        
        self.leaderboard_table = QTableWidget(self.lead_box)
        self.leaderboard_table.setColumnCount(3)
        self.leaderboard_table.setHorizontalHeaderLabels(["الطيار", "الفواتير", "إجمالي المبيعات"])
        self.leaderboard_table.setStyleSheet("QTableWidget { background: transparent; border: none; } QHeaderView::section { background-color: #081211; color: white; padding: 4px; font-size: 11px; }")
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.leaderboard_table.verticalHeader().setVisible(False)
        lead_layout.addWidget(self.leaderboard_table)
        charts_layout.addWidget(self.lead_box, stretch=2)
        
        overview_layout.addLayout(charts_layout)
        self.tabs.addTab(tab_overview, "نظرة عامة وإحصائيات")
        
        # ── Tab 2: Detailed Order History ──
        tab_history = QWidget()
        history_layout = QVBoxLayout(tab_history)
        history_layout.setContentsMargins(10, 10, 10, 10)
        history_layout.setSpacing(10)
        
        # Search filter bar
        search_bar = QHBoxLayout()
        search_lbl = QLabel("🔍 بحث في السجل:", tab_history)
        search_lbl.setStyleSheet("font-weight: bold; color: rgba(255,255,255,0.6);")
        search_bar.addWidget(search_lbl)
        
        self.search_input = QLineEdit(tab_history)
        self.search_input.setPlaceholderText("رقم الأوردر، تليفون العميل، أو اسم الطيار...")
        self.search_input.setFixedHeight(34)
        self.search_input.textChanged.connect(self.search_history)
        search_bar.addWidget(self.search_input)
        history_layout.addLayout(search_bar)
        
        # History table
        self.history_table = QTableWidget(tab_history)
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels(["الفاتورة", "التاريخ والوقت", "القناة", "طريقة الدفع", "الإجمالي", "الحالة", "إجراء"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.verticalHeader().setVisible(False)
        history_layout.addWidget(self.history_table)
        
        self.tabs.addTab(tab_history, "سجل الفواتير والطلبات")
        layout.addWidget(self.tabs)

    def create_stat_card(self, title_txt, val_txt, val_color):
        card = QFrame(self)
        card.setStyleSheet("background-color: rgba(255,255,255,0.02); border: 1px solid #263434; border-radius: 8px; padding: 10px;")
        lyt = QVBoxLayout(card)
        lyt.setSpacing(4)
        
        lbl_t = QLabel(title_txt, card)
        lbl_t.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px; border: none; background: transparent;")
        lyt.addWidget(lbl_t)
        
        lbl_v = QLabel(val_txt, card)
        lbl_v.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {val_color}; border: none; background: transparent;")
        lyt.addWidget(lbl_v)
        
        card.setProperty("label_widget", lbl_v)
        return card

    def change_filter(self, new_range):
        self.filter_range = new_range
        self.btn_day.setChecked(new_range == "day")
        self.btn_week.setChecked(new_range == "week")
        self.btn_month.setChecked(new_range == "month")
        
        self.load_analytics()

    def search_history(self):
        self.load_analytics()

    def load_analytics(self):
        now = datetime.now()
        if self.filter_range == "day":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self.filter_range == "week":
            start_date = now - timedelta(days=7)
        else: # month
            start_date = now - timedelta(days=30)
            
        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        
        conn = database.get_connection()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*), SUM(total) FROM orders WHERE status='COMPLETED' AND created_at >= ?", (start_str,))
        o_cnt, total_sales = c.fetchone()
        total_sales = total_sales if total_sales else 0.0
        
        self.card_sales.property("label_widget").setText(f"{total_sales:,.2f} ج.م")
        self.card_orders.property("label_widget").setText(str(o_cnt))
        
        c.execute("""
            SELECT m.name, SUM(oi.quantity) as q
            FROM order_items oi
            JOIN menu_items m ON oi.menu_item_id = m.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status='COMPLETED' AND o.created_at >= ?
            GROUP BY oi.menu_item_id
            ORDER BY q DESC LIMIT 1
        """, (start_str,))
        best_dish = c.fetchone()
        best_dish_txt = best_dish[0] if best_dish else "لا يوجد"
        self.card_dish.property("label_widget").setText(best_dish_txt)
        
        c.execute("""
            SELECT strftime('%H', created_at) as hr, COUNT(*) as c
            FROM orders
            WHERE status='COMPLETED' AND created_at >= ?
            GROUP BY hr
            ORDER BY c DESC LIMIT 1
        """, (start_str,))
        peak_hour = c.fetchone()
        if peak_hour:
            h = int(peak_hour[0])
            period = "مساءً" if h >= 12 else "صباحاً"
            disp_h = h - 12 if h > 12 else (h if h > 0 else 12)
            peak_txt = f"{disp_h}:00 {period}"
        else:
            peak_txt = "لا يوجد"
        self.card_hour.property("label_widget").setText(peak_txt)
        
        c.execute("""
            SELECT channel, SUM(total)
            FROM orders
            WHERE status='COMPLETED' AND created_at >= ?
            GROUP BY channel
        """, (start_str,))
        channels_sales = dict(c.fetchall())
        cashier_sales = channels_sales.get("CASHIER", 0.0)
        delivery_sales = channels_sales.get("DELIVERY", 0.0)
        
        while self.bars_layout.count():
            child = self.bars_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        c_pct = int((cashier_sales / (cashier_sales + delivery_sales) * 100)) if (cashier_sales + delivery_sales) > 0 else 0
        d_pct = 100 - c_pct if (cashier_sales + delivery_sales) > 0 else 0
        
        c_bar = QFrame(self.bars_container)
        c_bar.setStyleSheet("border: none; background: transparent;")
        c_bar_lyt = QHBoxLayout(c_bar)
        c_bar_lyt.setContentsMargins(0,0,0,0)
        lbl_cb = QLabel("الصالة والتيك أواي:", c_bar)
        lbl_cb.setFixedWidth(110)
        c_bar_lyt.addWidget(lbl_cb)
        c_bar_val = QLabel(f"{cashier_sales:,.1f} ج.م ({c_pct}%)", c_bar)
        c_bar_val.setStyleSheet("color: #8cffa7; font-weight: bold; border: none; background: transparent;")
        c_bar_lyt.addWidget(c_bar_val)
        self.bars_layout.addWidget(c_bar)
        
        d_bar = QFrame(self.bars_container)
        d_bar.setStyleSheet("border: none; background: transparent;")
        d_bar_lyt = QHBoxLayout(d_bar)
        d_bar_lyt.setContentsMargins(0,0,0,0)
        lbl_db = QLabel("خدمة الدليفري:", d_bar)
        lbl_db.setFixedWidth(110)
        d_bar_lyt.addWidget(lbl_db)
        d_bar_val = QLabel(f"{delivery_sales:,.1f} ج.م ({d_pct}%)", d_bar)
        d_bar_val.setStyleSheet("color: #a8deff; font-weight: bold; border: none; background: transparent;")
        d_bar_lyt.addWidget(d_bar_val)
        self.bars_layout.addWidget(d_bar)
        
        c.execute("""
            SELECT d.name, COUNT(o.id) as orders_delivered, SUM(o.total) as s
            FROM orders o
            JOIN drivers d ON o.driver_id = d.id
            WHERE o.status='COMPLETED' AND o.created_at >= ?
            GROUP BY o.driver_id
            ORDER BY orders_delivered DESC
        """, (start_str,))
        drivers_data = c.fetchall()
        
        self.leaderboard_table.setRowCount(len(drivers_data))
        for r_idx, (name, count, total) in enumerate(drivers_data):
            self.leaderboard_table.setItem(r_idx, 0, QTableWidgetItem(name))
            self.leaderboard_table.setItem(r_idx, 1, QTableWidgetItem(f"{count} أوردر"))
            self.leaderboard_table.setItem(r_idx, 2, QTableWidgetItem(f"{total:,.2f} ج.م"))
            
        q = self.search_input.text().strip()
        if q:
            c.execute("""
                SELECT o.id, o.created_at, o.channel, o.payment_method, o.total, o.status, COALESCE(cust.name, 'صالة')
                FROM orders o
                LEFT JOIN customers cust ON o.customer_id = cust.id
                LEFT JOIN drivers d ON o.driver_id = d.id
                WHERE o.created_at >= ? AND (o.id LIKE ? OR cust.phone LIKE ? OR cust.name LIKE ? OR d.name LIKE ?)
                ORDER BY o.id DESC
            """, (start_str, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
        else:
            c.execute("""
                SELECT o.id, o.created_at, o.channel, o.payment_method, o.total, o.status, COALESCE(cust.name, 'صالة')
                FROM orders o
                LEFT JOIN customers cust ON o.customer_id = cust.id
                WHERE o.created_at >= ?
                ORDER BY o.id DESC
            """, (start_str,))
            
        history_rows = c.fetchall()
        conn.close()
        
        self.history_table.setRowCount(len(history_rows))
        for r_idx, (o_id, created_at, chan, pay_method, total, status, name) in enumerate(history_rows):
            self.history_table.setItem(r_idx, 0, QTableWidgetItem(f"#{o_id}"))
            
            dt = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
            self.history_table.setItem(r_idx, 1, QTableWidgetItem(dt.strftime("%d/%m %I:%M %p")))
            
            chan_str = "🛵 دليفري" if chan == 'DELIVERY' else "🏠 صالة"
            self.history_table.setItem(r_idx, 2, QTableWidgetItem(chan_str))
            
            pay_str = "نقدي كاش" if pay_method == 'CASH' else ("فيزا" if pay_method == 'VISA' else "محفظة")
            self.history_table.setItem(r_idx, 3, QTableWidgetItem(pay_str))
            
            self.history_table.setItem(r_idx, 4, QTableWidgetItem(f"{total:,.2f} ج"))
            
            status_str = "نشط" if status in ('PENDING', 'DISPATCHED') else "مكتمل"
            self.history_table.setItem(r_idx, 5, QTableWidgetItem(status_str))
            
            # Create a cell widget layout for multiple buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(6)

            btn_view = QPushButton("🖨 عرض", actions_widget)
            btn_view.setFixedHeight(24)
            btn_view.setStyleSheet(
                "QPushButton { background: rgba(168,222,255,0.06); color: #a8deff; "
                "border: 1px solid rgba(168,222,255,0.3); border-radius: 4px; "
                "font-size: 10px; padding: 0px 4px; font-weight: bold; } "
                "QPushButton:hover { background: #a8deff; color: #0e1e1d; }"
            )
            btn_view.clicked.connect(lambda checked, idx=o_id: self.view_order_receipt(idx))
            actions_layout.addWidget(btn_view)

            btn_del = QPushButton("🗑️ حذف", actions_widget)
            btn_del.setFixedHeight(24)
            btn_del.setStyleSheet(
                "QPushButton { background: rgba(255,80,80,0.06); color: #ff6b6b; "
                "border: 1px solid rgba(255,80,80,0.3); border-radius: 4px; "
                "font-size: 10px; padding: 0px 4px; font-weight: bold; } "
                "QPushButton:hover { background: #ff5050; color: white; }"
            )
            btn_del.clicked.connect(lambda checked, idx=o_id: self.delete_order_from_reports(idx))
            actions_layout.addWidget(btn_del)

            self.history_table.setCellWidget(r_idx, 6, actions_widget)

    def view_order_receipt(self, order_id):
        parent = self.parent()
        if parent and hasattr(parent, 'generate_receipt_text'):
            cashier_receipt = parent.generate_receipt_text(order_id, "نسخة الكاشير (نسخة سابقة)")
            kitchen_receipt = parent.generate_receipt_text(order_id, "نسخة المطبخ (نسخة سابقة)")
            psim = ReceiptSimDialog(order_id, cashier_receipt, kitchen_receipt, parent)
            psim.exec()
        else:
            QMessageBox.warning(self, "خطأ", "لا يمكن تشغيل طابعة المحاكاة للفواتير السابقة.")

    def delete_order_from_reports(self, order_id):
        parent = self.parent()
        if parent and hasattr(parent, 'delete_order_action'):
            parent.delete_order_action(order_id)
            self.load_analytics()



class ShiftClosingDialog(QDialog):
    """Cash Register Shift closing report verification with premium, luxurious design."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إغلاق الوردية والدرج")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(420, 500)
        self.setStyleSheet(STYLE_SHEET)
        
        self.shift_closed = False
        self.expected_cash = 0.0
        
        self.init_ui()
        self.calculate_shift_summary()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Header block
        header = QHBoxLayout()
        title = QLabel("🔑  إغلاق الوردية والدرج المالي", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffd9a8; border: none; background: transparent;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(26, 26)
        btn_close.setStyleSheet("QPushButton { background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.6); border: 1px solid #263434; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; border-color: #ffa8f6; }")
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        layout.addLayout(header)
        
        # LCD Expected Cash Box
        exp_box = QFrame(self)
        exp_box.setObjectName("ExpBox")
        exp_box.setStyleSheet("""
            QFrame#ExpBox {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(140,255,167,0.02), stop:1 rgba(140,255,167,0.05));
                border: 1.5px solid rgba(140, 255, 167, 0.25);
                border-radius: 8px;
            }
        """)
        exp_lyt = QVBoxLayout(exp_box)
        exp_lyt.setContentsMargins(12, 12, 12, 12)
        exp_lyt.setSpacing(4)
        exp_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_e = QLabel("💵  الكاش المتوقع وجوده في الدرج", exp_box)
        lbl_e.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px; font-weight: bold; border: none; background: transparent;")
        lbl_e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exp_lyt.addWidget(lbl_e)
        
        self.val_exp_cash = QLabel("0.00 ج.م", exp_box)
        self.val_exp_cash.setStyleSheet("font-size: 26px; font-weight: bold; color: #8cffa7; border: none; background: transparent;")
        self.val_exp_cash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exp_lyt.addWidget(self.val_exp_cash)
        layout.addWidget(exp_box)
        
        # Summary Box
        self.summary_box = QFrame(self)
        self.summary_box.setObjectName("SummaryBox")
        self.summary_box.setStyleSheet("""
            QFrame#SummaryBox {
                background: rgba(255,255,255,0.01); 
                border: 1px solid #263434; 
                border-radius: 8px;
            }
        """)
        self.summary_lyt = QVBoxLayout(self.summary_box)
        self.summary_lyt.setSpacing(6)
        self.summary_lyt.setContentsMargins(12, 12, 12, 12)
        
        # Summary Box Title
        lbl_summary_title = QLabel("📊 ملخص مبيعات وردية العمل الحالية", self.summary_box)
        lbl_summary_title.setStyleSheet("font-size: 11px; font-weight: bold; color: rgba(255,255,255,0.4); border: none; background: transparent; padding-bottom: 2px;")
        self.summary_lyt.addWidget(lbl_summary_title)
        
        layout.addWidget(self.summary_box)
        
        # Input Actual Money Block
        input_container = QFrame(self)
        input_container.setStyleSheet("border: none; background: transparent;")
        input_lyt = QVBoxLayout(input_container)
        input_lyt.setContentsMargins(0, 2, 0, 0)
        input_lyt.setSpacing(6)
        
        lbl_act = QLabel("🔍 اكتب المبلغ الفعلي المتواجد بالدرج حالياً للتحقق والاستلام:", input_container)
        lbl_act.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px; font-weight: bold; border: none; background: transparent;")
        lbl_act.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        input_lyt.addWidget(lbl_act)
        
        self.actual_input = QLineEdit(input_container)
        self.actual_input.setPlaceholderText("أدخل المبلغ الفعلي...")
        self.actual_input.setFixedHeight(38)
        self.actual_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actual_input.setStyleSheet("""
            QLineEdit {
                font-size: 16px; 
                font-weight: bold; 
                background: #040808; 
                border: 1.5px solid #263434; 
                border-radius: 6px; 
                color: #ffffff; 
                padding: 2px;
            } 
            QLineEdit:focus { 
                border: 1.5px solid #ffd9a8; 
            }
        """)
        input_lyt.addWidget(self.actual_input)
        layout.addWidget(input_container)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        
        btn_cancel = QPushButton("تراجع وإلغاء", self)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.02);
                color: rgba(255,255,255,0.7);
                border: 1px solid #263434;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.06);
                color: white;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_confirm = QPushButton("🔒 تأكيد قفل الوردية والدرج", self)
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffd9a8, stop:1 #ffd9a8);
                color: #0e1e1d;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: white;
                color: #0e1e1d;
            }
        """)
        self.btn_confirm.clicked.connect(self.close_shift)
        
        btn_layout.addWidget(btn_cancel, stretch=1)
        btn_layout.addWidget(self.btn_confirm, stretch=2)
        layout.addLayout(btn_layout)

    def calculate_shift_summary(self):
        global ACTIVE_SHIFT_ID
        if not ACTIVE_SHIFT_ID:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        
        # Calculate sums of cashier/delivery orders in this shift
        c.execute("""
            SELECT payment_method, SUM(total)
            FROM orders
            WHERE shift_id=? AND status='COMPLETED'
            GROUP BY payment_method
        """, (ACTIVE_SHIFT_ID,))
        sales_by_pay = dict(c.fetchall())
        
        cash_sales = sales_by_pay.get("CASH", 0.0)
        visa_sales = sales_by_pay.get("VISA", 0.0)
        wallet_sales = sales_by_pay.get("WALLET", 0.0)
        total_sales = cash_sales + visa_sales + wallet_sales
        
        self.expected_cash = cash_sales
        self.val_exp_cash.setText(f"{self.expected_cash:,.2f} ج.م")
        
        # Build premium custom rows
        self.add_summary_row("💵  مدفوعات كاش نقدي", f"{cash_sales:,.2f} ج.م", "#8cffa7")
        self.add_summary_row("💳  مدفوعات فيزا وكروت", f"{visa_sales:,.2f} ج.م", "#a8deff")
        self.add_summary_row("📱  محفظة إلكترونية", f"{wallet_sales:,.2f} ج.م", "#ffa8f6")
        
        # Separator line
        sep = QFrame(self.summary_box)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #263434; max-height: 1px; border: none;")
        self.summary_lyt.addWidget(sep)
        
        self.add_summary_row("📊  إجمالي مبيعات الوردية", f"{total_sales:,.2f} ج.م", "#ffd9a8", is_bold=True)
        
        conn.close()
        
    def add_summary_row(self, label_txt, val_txt, val_color, is_bold=False):
        row = QFrame(self.summary_box)
        row.setStyleSheet("background: transparent; border: none;")
        row_lyt = QHBoxLayout(row)
        row_lyt.setContentsMargins(0, 0, 0, 0)
        
        lbl = QLabel(label_txt, row)
        font_sz = "12px" if is_bold else "11px"
        font_w = "bold" if is_bold else "normal"
        lbl.setStyleSheet(f"color: rgba(255,255,255,0.7); font-size: {font_sz}; font-weight: {font_w}; border: none; background: transparent;")
        row_lyt.addWidget(lbl)
        
        row_lyt.addStretch()
        
        val = QLabel(val_txt, row)
        val_sz = "13px" if is_bold else "12px"
        val.setStyleSheet(f"color: {val_color}; font-size: {val_sz}; font-weight: bold; border: none; background: transparent;")
        row_lyt.addWidget(val)
        
        self.summary_lyt.addWidget(row)

    def close_shift(self):
        global ACTIVE_SHIFT_ID

    def close_shift(self):
        global ACTIVE_SHIFT_ID
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
                cash_sales = (SELECT COALESCE(SUM(total), 0) FROM orders WHERE shift_id=? AND status='COMPLETED' AND payment_method='CASH'),
                visa_sales = (SELECT COALESCE(SUM(total), 0) FROM orders WHERE shift_id=? AND status='COMPLETED' AND payment_method='VISA'),
                wallet_sales = (SELECT COALESCE(SUM(total), 0) FROM orders WHERE shift_id=? AND status='COMPLETED' AND payment_method='WALLET'),
                total_sales = (SELECT COALESCE(SUM(total), 0) FROM orders WHERE shift_id=? AND status='COMPLETED')
            WHERE id = ?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), actual_cash, ACTIVE_SHIFT_ID, ACTIVE_SHIFT_ID, ACTIVE_SHIFT_ID, ACTIVE_SHIFT_ID, ACTIVE_SHIFT_ID))
        
        conn.commit()
        conn.close()
        
        ACTIVE_SHIFT_ID = None
        self.shift_closed = True
        self.accept()


class ReceiptSimDialog(QDialog):
    """Displays double receipts (Kitchen copy & Cashier copy) before actual hard copy printing."""
    def __init__(self, order_id, cashier_text, kitchen_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("محاكاة طباعة الفاتورة")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(560, 480)
        self.setStyleSheet(STYLE_SHEET)
        
        self.order_id = order_id
        self.cashier_text = cashier_text
        self.kitchen_text = kitchen_text
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel("محاكاة طباعة نسختي الفاتورة (نسخة كاشير + نسخة مطبخ)", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #8cffa7;")
        layout.addWidget(title)
        
        # Dual layout scrolls
        dual = QHBoxLayout()
        dual.setSpacing(14)
        
        # Cashier strip
        c_box = QVBoxLayout()
        c_box.addWidget(QLabel("نسخة العميل / الكاشير:", self))
        self.c_text = QTextEdit(self)
        self.c_text.setReadOnly(True)
        self.c_text.setText(self.cashier_text)
        self.c_text.setStyleSheet("background: white; color: black; font-family: 'Courier New', monospace; font-size: 11px;")
        c_box.addWidget(self.c_text)
        dual.addLayout(c_box)
        
        # Kitchen strip
        k_box = QVBoxLayout()
        k_box.addWidget(QLabel("نسخة المطبخ وتحضير الطعام:", self))
        self.k_text = QTextEdit(self)
        self.k_text.setReadOnly(True)
        self.k_text.setText(self.kitchen_text)
        self.k_text.setStyleSheet("background: white; color: black; font-family: 'Courier New', monospace; font-size: 11px;")
        k_box.addWidget(self.k_text)
        dual.addLayout(k_box)
        
        layout.addLayout(dual)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_hard_print = QPushButton("طباعة ورقية حقيقية", self)
        self.btn_hard_print.clicked.connect(self.trigger_hard_print)
        
        self.btn_reprint = QPushButton("إعادة طباعة (Reprint)", self)
        self.btn_reprint.setObjectName("BtnOrange")
        self.btn_reprint.clicked.connect(self.reprint_action)
        
        btn_done = QPushButton("تم الحفظ والإغلاق", self)
        btn_done.setObjectName("BtnDark")
        btn_done.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_done)
        btn_layout.addWidget(self.btn_reprint)
        btn_layout.addWidget(self.btn_hard_print)
        layout.addLayout(btn_layout)

    def trigger_hard_print(self):
        if not PRINTER_ONLINE:
            QMessageBox.critical(self, "خطأ بالطابعة", "تنبيه: تعذر إرسال الأمر! طابعة الفواتير غير متصلة أو انقطع اتصال الكابل.")
            return
            
        # Simulated physical printing integration (QPrinter/native window)
        QMessageBox.information(self, "طابعة النظام", "تم إرسال الفاتورة بنجاح إلى طابعة الويندوز الافتراضية.")
        
    def reprint_action(self):
        if not PRINTER_ONLINE:
            QMessageBox.critical(self, "خطأ بالطابعة", "تنبيه: تعذر إرسال الأمر! طابعة الفواتير غير متصلة أو انقطع اتصال الكابل.")
            return
        QMessageBox.information(self, "طابعة النظام", "جاري إعادة طباعة الفاتورة السابقة...")


class MainPOSDashboard(QMainWindow):
    """Main Restaurant checkout dashboard window."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("مطعم بروست - نظام الكاشير والدليفري الذكي")
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(STYLE_SHEET)
        
        # Order cart variables
        self.active_channel = "cashier" # cashier / delivery
        self.payment_method = "cash"
        
        self.current_customer_id = None
        self.current_customer_name = ""
        self.current_customer_address = ""
        
        self.cart_items = [] # list of dicts: {id, name, size, extras: {name: price}, base_price, qty}
        
        self.init_ui()
        self.ensure_active_shift()
        self.load_categories()
        self.load_popular_items()
        self.load_menu_items(None)
        self.load_pending_delivery_orders()
        
        # Periodic check for delayed active orders (every 5 seconds)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_pending_orders_timers)
        self.timer.start(5000)
        
        # Automatic backups trigger once a day
        self.run_automated_daily_backup()

    def init_ui(self):
        # Frameless main wrapper
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # [1] Custom titlebar
        self.title_bar = CustomTitleBar(self)
        self.main_layout.addWidget(self.title_bar)
        
        # [2] Stacked widget
        self.stacked_widget = QStackedWidget(self.main_widget)
        self.main_layout.addWidget(self.stacked_widget)
        
        # --- Page 0: Login Page ---
        self.login_page = QWidget(self.stacked_widget)
        self.setup_login_ui()
        self.stacked_widget.addWidget(self.login_page)
        
        # --- Page 1: POS Main Page ---
        self.pos_page = QWidget(self.stacked_widget)
        self.pos_layout = QVBoxLayout(self.pos_page)
        self.pos_layout.setContentsMargins(0, 0, 0, 0)
        self.pos_layout.setSpacing(0)
        self.stacked_widget.addWidget(self.pos_page)
        
        # [2] App Header Controls Bar
        self.header_bar = QFrame(self.pos_page)
        self.header_bar.setObjectName("TitleBar")
        self.header_bar.setFixedHeight(65)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(15, 0, 15, 0)
        
        # Top-left of header bar: Collapsible Active Delivery Orders and Printer Simulator
        self.btn_toggle_orders = QPushButton("الطلبـات الجاريـة 🔔 (0)", self.header_bar)
        self.btn_toggle_orders.setStyleSheet("QPushButton { background-color: rgba(255, 255, 255, 0.04); color: white; border: 1px solid #263434; border-radius: 4px; padding: 6px 12px; font-weight: bold; }")
        self.btn_toggle_orders.clicked.connect(self.toggle_active_orders_sidebar)
        header_layout.addWidget(self.btn_toggle_orders)
        
        # Printer Status simulator button
        self.btn_printer_status = QPushButton("طابعة المطبخ والكاشير: متصلة", self.header_bar)
        self.btn_printer_status.setStyleSheet("QPushButton { background-color: rgba(140, 255, 167, 0.05); color: #8cffa7; border: 1px solid rgba(140, 255, 167, 0.2); border-radius: 4px; padding: 6px 12px; font-weight: bold; }")
        self.btn_printer_status.clicked.connect(self.toggle_printer_connection_sim)
        header_layout.addWidget(self.btn_printer_status)
        
        header_layout.addStretch()
        
        # Action/Admin tools (RTL aligned via layout flow)
        btn_drivers_mgr = QPushButton("🛵 الطيارين", self.header_bar)
        btn_drivers_mgr.setObjectName("BtnBlue")
        btn_drivers_mgr.clicked.connect(self.open_drivers_management)
        header_layout.addWidget(btn_drivers_mgr)
        
        btn_menu_mgr = QPushButton("🔧 إدارة المنيو", self.header_bar)
        btn_menu_mgr.setObjectName("BtnDark")
        btn_menu_mgr.clicked.connect(self.open_menu_management)
        header_layout.addWidget(btn_menu_mgr)
        
        btn_reports = QPushButton("📊 لوحة التقارير", self.header_bar)
        btn_reports.setObjectName("BtnOrange")
        btn_reports.clicked.connect(self.open_reports_dialog)
        header_layout.addWidget(btn_reports)
        
        btn_backup = QPushButton("☁️ نسخة احتياطية", self.header_bar)
        btn_backup.setObjectName("BtnDark")
        btn_backup.clicked.connect(self.trigger_manual_backup)
        header_layout.addWidget(btn_backup)
        
        btn_close_shift = QPushButton("🚪 إغلاق الوردية", self.header_bar)
        btn_close_shift.setObjectName("BtnPink")
        btn_close_shift.clicked.connect(self.close_shift_and_drawer)
        header_layout.addWidget(btn_close_shift)
        
        # User & Settings Profile icons far-right
        btn_user_profile = QPushButton("👤", self.header_bar)
        btn_user_profile.setFixedSize(38, 38)
        btn_user_profile.setStyleSheet("QPushButton { background-color: rgba(255,255,255,0.04); color: white; border: 1px solid #263434; border-radius: 6px; font-size: 16px; padding: 0px; }")
        header_layout.addWidget(btn_user_profile)
        
        btn_settings = QPushButton("⚙️", self.header_bar)
        btn_settings.setFixedSize(38, 38)
        btn_settings.setStyleSheet("QPushButton { background-color: rgba(255,255,255,0.04); color: white; border: 1px solid #263434; border-radius: 6px; font-size: 16px; padding: 0px; }")
        btn_settings.clicked.connect(self.open_menu_management)
        header_layout.addWidget(btn_settings)
        
        self.pos_layout.addWidget(self.header_bar)
        
        # [3] POS Grid columns
        pos_body = QWidget(self.pos_page)
        pos_layout = QHBoxLayout(pos_body)
        pos_layout.setContentsMargins(10, 10, 10, 10)
        pos_layout.setSpacing(10)
        
        # Column A: Active Orders Panel (right side - collapsible)
        self.left_col = QFrame(pos_body)
        self.left_col.setObjectName("PosPanel")
        self.left_col.setFixedWidth(300)
        left_layout = QVBoxLayout(self.left_col)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        
        # Panel header with live count badge
        left_hdr = QHBoxLayout()
        left_hdr.setSpacing(8)
        
        live_dot = QLabel("●", self.left_col)
        live_dot.setStyleSheet("color: #8cffa7; font-size: 10px; border: none; background: transparent;")
        left_hdr.addWidget(live_dot)
        
        left_title = QLabel("الطلبات الجارية", self.left_col)
        left_title.setStyleSheet("font-weight: 900; font-size: 14px; color: white; border: none; background: transparent;")
        left_hdr.addWidget(left_title)
        left_hdr.addStretch()
        
        self.orders_count_badge = QLabel("0", self.left_col)
        self.orders_count_badge.setStyleSheet(
            "background: rgba(140,255,167,0.12); color: #8cffa7; "
            "border: 1px solid rgba(140,255,167,0.3); border-radius: 10px; "
            "padding: 1px 10px; font-weight: bold; font-size: 12px;"
        )
        self.orders_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_hdr.addWidget(self.orders_count_badge)
        
        left_layout.addLayout(left_hdr)
        
        # Thin separator line
        sep = QFrame(self.left_col)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(255,255,255,0.07); border: none; max-height: 1px;")
        left_layout.addWidget(sep)
        
        # Scrollable orders area
        self.scroll_orders = QScrollArea(self.left_col)
        self.scroll_orders.setWidgetResizable(True)
        self.scroll_orders.setStyleSheet("background: transparent; border: none;")
        self.scroll_orders.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.orders_container = QWidget()
        self.orders_container.setStyleSheet("background: transparent;")
        self.orders_layout = QVBoxLayout(self.orders_container)
        self.orders_layout.setContentsMargins(0, 0, 4, 0)
        self.orders_layout.setSpacing(8)
        # IMPORTANT: alignment top so cards stack from the top
        self.orders_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_orders.setWidget(self.orders_container)
        left_layout.addWidget(self.scroll_orders)
        

        
        # Column B: Center Menu items block
        self.center_col = QWidget(pos_body)
        center_layout = QVBoxLayout(self.center_col)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)
        
        # Popular row
        pop_row = QHBoxLayout()
        pop_row.addWidget(QLabel("الـ 5 أصناف الأكثر طلباً 🔥:", self.center_col))
        self.pop_buttons_widget = QWidget(self.center_col)
        self.pop_buttons_layout = QHBoxLayout(self.pop_buttons_widget)
        self.pop_buttons_layout.setContentsMargins(0,0,0,0)
        self.pop_buttons_layout.setSpacing(6)
        pop_row.addWidget(self.pop_buttons_widget)
        pop_row.addStretch()
        center_layout.addLayout(pop_row)
        
        # Grid menu scroll area
        self.scroll_menu = QScrollArea(self.center_col)
        self.scroll_menu.setWidgetResizable(True)
        self.scroll_menu.setStyleSheet("background: transparent; border: 1px solid #263434; border-radius: 12px;")
        self.menu_container = QWidget()
        self.menu_grid = QGridLayout(self.menu_container)
        self.menu_grid.setContentsMargins(10, 10, 10, 10)
        self.menu_grid.setSpacing(10)
        self.scroll_menu.setWidget(self.menu_container)
        center_layout.addWidget(self.scroll_menu)
        
        # Column D: Categories Vertical Sidebar (Left side, LTR flow) - 200px width
        self.categories_sidebar = QFrame(pos_body)
        self.categories_sidebar.setObjectName("PosPanel")
        self.categories_sidebar.setFixedWidth(200)
        sidebar_main_layout = QVBoxLayout(self.categories_sidebar)
        sidebar_main_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_main_layout.setSpacing(12)
        
        # [A] Sidebar Top Drawer & Brand Header
        drawer_row = QHBoxLayout()
        drawer_row.setSpacing(6)
        
        self.lbl_drawer_cash = QLabel("الدرج: 0.00 ج.م", self.categories_sidebar)
        self.lbl_drawer_cash.setStyleSheet("background-color: rgba(255,255,255,0.04); border: 1px solid #263434; border-radius: 4px; padding: 6px 12px; font-weight: bold; color: white;")
        self.lbl_drawer_cash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drawer_row.addWidget(self.lbl_drawer_cash, stretch=4)
        
        self.btn_edit_drawer = QPushButton("✏️", self.categories_sidebar)
        self.btn_edit_drawer.setToolTip("تعديل مبلغ الدرج يدوياً")
        self.btn_edit_drawer.setFixedSize(32, 32)
        self.btn_edit_drawer.setObjectName("BtnBlue")
        self.btn_edit_drawer.setStyleSheet("font-size: 12px; padding: 0;")
        self.btn_edit_drawer.clicked.connect(self.manually_edit_drawer_cash)
        drawer_row.addWidget(self.btn_edit_drawer, stretch=1)
        
        sidebar_main_layout.addLayout(drawer_row)
        
        brand_title = QLabel("نظام الكاشير", self.categories_sidebar)
        brand_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #8cffa7; border: none; background: transparent;")
        brand_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_main_layout.addWidget(brand_title)
        
        title_hdr = QLabel("القائمة", self.categories_sidebar)
        title_hdr.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; border: none; background: transparent;")
        title_hdr.setAlignment(Qt.AlignmentFlag.AlignRight)
        sidebar_main_layout.addWidget(title_hdr)
        
        subtitle_hdr = QLabel("تصنيفات الطعام", self.categories_sidebar)
        subtitle_hdr.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.5); border: none; background: transparent;")
        subtitle_hdr.setAlignment(Qt.AlignmentFlag.AlignRight)
        sidebar_main_layout.addWidget(subtitle_hdr)
        
        # [B] Categories Dynamic Buttons Area
        self.categories_container = QWidget(self.categories_sidebar)
        self.categories_container.setStyleSheet("border: none; background: transparent;")
        self.cat_sidebar_layout = QVBoxLayout(self.categories_container)
        self.cat_sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.cat_sidebar_layout.setSpacing(8)
        sidebar_main_layout.addWidget(self.categories_container)
        
        sidebar_main_layout.addStretch()
        
        # [C] Sidebar Bottom Controls
        btn_open_shift_manual = QPushButton("+ فتح وردية جديدة", self.categories_sidebar)
        btn_open_shift_manual.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #8cffa7;
                border: 2px dashed rgba(140, 255, 167, 0.4); border-radius: 6px;
                padding: 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(140, 255, 167, 0.05); border-color: #8cffa7; }
        """)
        btn_open_shift_manual.clicked.connect(self.close_shift_and_drawer)
        sidebar_main_layout.addWidget(btn_open_shift_manual)
        
        footer_layout = QHBoxLayout()
        lbl_version = QLabel("V1.0.0 STABLE", self.categories_sidebar)
        lbl_version.setStyleSheet("color: rgba(255,255,255,0.3); font-size: 10px; font-weight: bold; border: none; background: transparent;")
        self.lbl_sidebar_time = QLabel("", self.categories_sidebar)
        self.lbl_sidebar_time.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 10px; font-weight: bold; border: none; background: transparent;")
        
        footer_layout.addWidget(lbl_version)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_sidebar_time)
        sidebar_main_layout.addLayout(footer_layout)
        

        
        # Column C: Right checkout cart (410px width)
        self.right_col = QFrame(pos_body)
        self.right_col.setObjectName("PosPanel")
        self.right_col.setFixedWidth(410)
        right_layout = QVBoxLayout(self.right_col)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)
        
        # Channel switches
        chan_layout = QHBoxLayout()
        chan_layout.setSpacing(6)
        self.btn_chan_cashier = QPushButton("صالة / تيك أواي", self.right_col)
        self.btn_chan_cashier.setObjectName("ChannelBtn")
        self.btn_chan_cashier.setProperty("active", True)
        self.btn_chan_cashier.setProperty("mode", "cashier")
        self.btn_chan_cashier.clicked.connect(lambda: self.switch_channel("cashier"))
        
        self.btn_chan_delivery = QPushButton("دليفري وتوصيل", self.right_col)
        self.btn_chan_delivery.setObjectName("ChannelBtn")
        self.btn_chan_delivery.setProperty("active", False)
        self.btn_chan_delivery.setProperty("mode", "delivery")
        self.btn_chan_delivery.clicked.connect(lambda: self.switch_channel("delivery"))
        
        chan_layout.addWidget(self.btn_chan_cashier)
        chan_layout.addWidget(self.btn_chan_delivery)
        right_layout.addLayout(chan_layout)
        
        # Customer lookup form (Shown only in delivery)
        self.cust_lookup_box = QFrame(self.right_col)
        self.cust_lookup_box.setStyleSheet("background: rgba(255,255,255,0.01); border: 1px dashed #263434; border-radius: 6px;")
        cust_layout = QVBoxLayout(self.cust_lookup_box)
        cust_layout.setSpacing(6)
        
        lookup_row = QHBoxLayout()
        self.cust_phone_input = QLineEdit(self.cust_lookup_box)
        self.cust_phone_input.setPlaceholderText("رقم موبايل العميل...")
        self.cust_phone_input.textChanged.connect(self.handle_phone_changed)
        lookup_row.addWidget(self.cust_phone_input)
        
        btn_cust_find = QPushButton("بحث", self.cust_lookup_box)
        btn_cust_find.setFixedSize(50, 32)
        btn_cust_find.clicked.connect(self.trigger_customer_search)
        lookup_row.addWidget(btn_cust_find)
        cust_layout.addLayout(lookup_row)
        
        self.cust_name_input = QLineEdit(self.cust_lookup_box)
        self.cust_name_input.setPlaceholderText("اسم العميل...")
        self.cust_name_input.textChanged.connect(self.handle_customer_details_edited)
        cust_layout.addWidget(self.cust_name_input)
        
        self.cust_addr_input = QTextEdit(self.cust_lookup_box)
        self.cust_addr_input.setPlaceholderText("عنوان التوصيل بالتفصيل...")
        self.cust_addr_input.setFixedHeight(50)
        self.cust_addr_input.textChanged.connect(self.handle_customer_details_edited)
        cust_layout.addWidget(self.cust_addr_input)
        
        # Repeat Previous Order button
        self.btn_repeat_order = QPushButton("كرر أوردر العميل السابق بزر واحد", self.cust_lookup_box)
        self.btn_repeat_order.setObjectName("BtnOrange")
        self.btn_repeat_order.setVisible(False)
        self.btn_repeat_order.clicked.connect(self.repeat_last_order_for_customer)
        cust_layout.addWidget(self.btn_repeat_order)
        
        right_layout.addWidget(self.cust_lookup_box)
        # Start visible, cashier mode defaults
        self.cust_addr_input.setVisible(False)
        self.cust_phone_input.setPlaceholderText("رقم الموبايل (اختياري)...")
        self.cust_name_input.setPlaceholderText("اسم العميل (إجباري)...")
        
        # Cart list
        right_layout.addWidget(QLabel("محتويات السلة الحالية:", self.right_col))
        self.scroll_cart = QScrollArea(self.right_col)
        self.scroll_cart.setWidgetResizable(True)
        self.scroll_cart.setStyleSheet("background: transparent; border: 1px solid #263434; border-radius: 8px;")
        self.cart_container = QWidget()
        self.cart_layout = QVBoxLayout(self.cart_container)
        self.cart_layout.setContentsMargins(6, 6, 6, 6)
        self.cart_layout.setSpacing(6)
        self.scroll_cart.setWidget(self.cart_container)
        right_layout.addWidget(self.scroll_cart)
        
        # Grand calculations
        calc_box = QWidget(self.right_col)
        calc_lyt = QVBoxLayout(calc_box)
        calc_lyt.setContentsMargins(0,0,0,0)
        
        sub_row = QHBoxLayout()
        sub_row.addWidget(QLabel("المجموع الفرعي:", calc_box))
        sub_row.addStretch()
        self.lbl_subtotal = QLabel("0.00 ج.م", calc_box)
        sub_row.addWidget(self.lbl_subtotal)
        calc_lyt.addLayout(sub_row)
        
        self.delivery_charge_row = QWidget(calc_box)
        dc_lyt = QHBoxLayout(self.delivery_charge_row)
        dc_lyt.setContentsMargins(0, 0, 0, 0)
        dc_lyt.addWidget(QLabel("عمولة التوصيل (الطيار):", self.delivery_charge_row))
        dc_lyt.addStretch()
        self.lbl_delivery_fee = QLabel("15.00 ج.م", self.delivery_charge_row)
        dc_lyt.addWidget(self.lbl_delivery_fee)
        calc_lyt.addWidget(self.delivery_charge_row)
        self.delivery_charge_row.setVisible(False)
        
        # Discount row input
        self.discount_charge_row = QWidget(calc_box)
        disc_lyt = QHBoxLayout(self.discount_charge_row)
        disc_lyt.setContentsMargins(0, 0, 0, 0)
        disc_lyt.addWidget(QLabel("خصم الفاتورة (ج.م):", self.discount_charge_row))
        disc_lyt.addStretch()
        self.discount_input = QLineEdit(self.discount_charge_row)
        self.discount_input.setPlaceholderText("0.0")
        self.discount_input.setFixedWidth(80)
        self.discount_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.discount_input.setStyleSheet("QLineEdit { background: #050a0a; border: 1.5px solid #263434; border-radius: 4px; color: #ffffff; padding: 2px; } QLineEdit:focus { border-color: #ffd9a8; }")
        self.discount_input.textChanged.connect(self.refresh_cart_display)
        disc_lyt.addWidget(self.discount_input)
        calc_lyt.addWidget(self.discount_charge_row)
        
        grand_row = QHBoxLayout()
        grand_lbl = QLabel("إجمالي الفاتورة لحظة بلحظة:", calc_box)
        grand_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        grand_row.addWidget(grand_lbl)
        grand_row.addStretch()
        self.lbl_grand_total = QLabel("0.00 ج.م", calc_box)
        self.lbl_grand_total.setObjectName("GrandTotalLabel")
        grand_row.addWidget(self.lbl_grand_total)
        calc_lyt.addLayout(grand_row)
        
        right_layout.addWidget(calc_box)
        
        # Payment types
        pay_row = QHBoxLayout()
        pay_row.setSpacing(4)
        self.btn_pay_cash = QPushButton("كاش / نقدي", self.right_col)
        self.btn_pay_cash.setCheckable(True)
        self.btn_pay_cash.setChecked(True)
        self.btn_pay_cash.clicked.connect(lambda: self.switch_payment_method("cash"))
        
        self.btn_pay_visa = QPushButton("فيزا كارت", self.right_col)
        self.btn_pay_visa.setCheckable(True)
        self.btn_pay_visa.clicked.connect(lambda: self.switch_payment_method("visa"))
        
        self.btn_pay_wallet = QPushButton("محفظة", self.right_col)
        self.btn_pay_wallet.setCheckable(True)
        self.btn_pay_wallet.clicked.connect(lambda: self.switch_payment_method("wallet"))
        
        pay_row.addWidget(self.btn_pay_cash)
        pay_row.addWidget(self.btn_pay_visa)
        pay_row.addWidget(self.btn_pay_wallet)
        right_layout.addLayout(pay_row)
        
        # Cash drawer presets
        self.cash_calc_widget = QWidget(self.right_col)
        self.cash_calc_lyt = QVBoxLayout(self.cash_calc_widget)
        self.cash_calc_lyt.setContentsMargins(0,0,0,0)
        self.cash_calc_lyt.setSpacing(4)
        
        in_row = QHBoxLayout()
        in_row.addWidget(QLabel("الكاش المدفوع:", self.cash_calc_widget))
        self.paid_input = QLineEdit(self.cash_calc_widget)
        self.paid_input.setPlaceholderText("0.0")
        self.paid_input.textChanged.connect(self.calculate_change_due)
        in_row.addWidget(self.paid_input)
        self.cash_calc_lyt.addLayout(in_row)
        
        # Quick presets row
        self.presets_widget = QWidget(self.cash_calc_widget)
        self.presets_lyt = QHBoxLayout(self.presets_widget)
        self.presets_lyt.setContentsMargins(0, 0, 0, 0)
        self.presets_lyt.setSpacing(4)
        
        presets = [50, 100, 200, 500]
        for val in presets:
            btn_pr = QPushButton(str(val), self.presets_widget)
            btn_pr.setStyleSheet("padding: 4px; font-size: 11px;")
            btn_pr.clicked.connect(lambda checked, v=val: self.apply_cash_preset(v))
            self.presets_lyt.addWidget(btn_pr)
            
        btn_exact = QPushButton("كامل المبلغ", self.presets_widget)
        btn_exact.setObjectName("BtnBlue")
        btn_exact.setStyleSheet("padding: 4px; font-size: 11px; font-weight: bold;")
        btn_exact.clicked.connect(self.apply_exact_cash)
        self.presets_lyt.addWidget(btn_exact)
        
        self.cash_calc_lyt.addWidget(self.presets_widget)
        
        out_row = QHBoxLayout()
        self.lbl_change_title = QLabel("الباقي للعميل:", self.cash_calc_widget)
        out_row.addWidget(self.lbl_change_title)
        out_row.addStretch()
        self.lbl_change_due = QLabel("0.00 ج.م", self.cash_calc_widget)
        self.lbl_change_due.setStyleSheet("font-weight: bold; color: #8cffa7;")
        out_row.addWidget(self.lbl_change_due)
        self.cash_calc_lyt.addLayout(out_row)
        
        right_layout.addWidget(self.cash_calc_widget)
        
        # Main submit checkout
        self.btn_submit_order = QPushButton("طباعة الفاتورة وتأكيد الدفع", self.right_col)
        self.btn_submit_order.setFixedHeight(48)
        self.btn_submit_order.clicked.connect(self.checkout_order)
        right_layout.addWidget(self.btn_submit_order)
        
        btn_clear_cart = QPushButton("تفريغ مسح السلة كاملة", self.right_col)
        btn_clear_cart.setObjectName("BtnPink")
        btn_clear_cart.clicked.connect(self.confirm_clear_cart)
        right_layout.addWidget(btn_clear_cart)
        
        # Horizontal layout alignment: Categories sidebar on the left, Center items middle, Cart right, Collapsible active orders far-right
        pos_layout.addWidget(self.categories_sidebar)
        pos_layout.addWidget(self.center_col)
        pos_layout.addWidget(self.right_col)
        pos_layout.addWidget(self.left_col)
        
        # Hide left_col (active delivery orders) by default to maximize items view
        self.left_col.setVisible(False)
        
        self.pos_layout.addWidget(pos_body)

    # ── LOGIN SYSTEM CONTROLS ──
    def setup_login_ui(self):
        layout = QVBoxLayout(self.login_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Outer alignment wrapper to center the card
        wrapper = QWidget(self.login_page)
        wrapper.setStyleSheet("background-color: #0e1e1d;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(20, 20, 20, 20)
        
        center_container = QFrame(wrapper)
        center_container.setObjectName("LoginCard")
        # Enforce exact dimensions for the login dialog card so it never stretches on high-res monitors
        center_container.setFixedSize(380, 530)
        center_container.setStyleSheet("""
            QFrame#LoginCard {
                background-color: #081211;
                border: 3px solid #263434;
                border-radius: 16px;
            }
        """)
        
        cc_layout = QVBoxLayout(center_container)
        cc_layout.setSpacing(14)
        cc_layout.setContentsMargins(30, 30, 30, 30)
        
        # Giant Premium Brand Header
        brand_label = QLabel("BROOST POS", center_container)
        brand_label.setStyleSheet("font-size: 32px; font-weight: 900; color: #8cffa7; letter-spacing: 2px; border: none; background: transparent;")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(brand_label)
        
        title_label = QLabel("نظام الكاشير والدليفري الذكي\nأدخل الرقم السري للفتح", center_container)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: rgba(255, 255, 255, 0.7); text-align: center; border: none; background: transparent; line-height: 140%;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(title_label)
        
        # Monospace Retro Computer Display Screen
        self.pin_display = QLineEdit(center_container)
        self.pin_display.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_display.setStyleSheet("""
            QLineEdit {
                font-family: 'Courier New', monospace;
                font-size: 28px;
                letter-spacing: 12px;
                text-align: center;
                background-color: #050a0a;
                border: 2px solid #263434;
                border-radius: 8px;
                padding: 10px;
                color: #8cffa7;
            }
            QLineEdit:focus {
                border-color: #8cffa7;
            }
        """)
        self.pin_display.setReadOnly(True)
        cc_layout.addWidget(self.pin_display)
        
        # Touch Keypad Grid (Styled mechanical style buttons)
        grid_widget = QWidget(center_container)
        grid_widget.setStyleSheet("border: none; background: transparent;")
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(0, 5, 0, 5)
        
        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح', 3, 0), ('0', 3, 1), ('دخول', 3, 2)
        ]
        
        for text, row, col in keys:
            btn = QPushButton(text, grid_widget)
            btn.setFixedSize(92, 54)
            
            # Mechanical style 3D cyber-brutalist buttons
            if text == 'دخول':
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 16px; font-weight: bold; background-color: #8cffa7; color: #0e1e1d;
                        border: 2px solid #263434; border-radius: 6px;
                    }
                    QPushButton:hover { background-color: #dcffe4; border-color: #8cffa7; }
                    QPushButton:pressed { background-color: #6ee68c; }
                """)
                btn.clicked.connect(self.submit_login)
            elif text == 'مسح':
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 14px; font-weight: bold; background-color: #ffd9a8; color: #0e1e1d;
                        border: 2px solid #263434; border-radius: 6px;
                    }
                    QPushButton:hover { background-color: #ffb755; border-color: #ffd9a8; }
                    QPushButton:pressed { background-color: #e59935; }
                """)
                btn.clicked.connect(self.clear_keys)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 18px; font-weight: bold; background-color: rgba(255,255,255,0.03); color: #ffffff;
                        border: 2px solid #263434; border-radius: 6px;
                    }
                    QPushButton:hover { background-color: rgba(255,255,255,0.1); border-color: #ffffff; }
                    QPushButton:pressed { background-color: rgba(255,255,255,0.15); }
                """)
                btn.clicked.connect(lambda checked, t=text: self.press_key(t))
                
            grid_layout.addWidget(btn, row, col)
            
        cc_layout.addWidget(grid_widget)
        
        # Removed lock screen default password label to make the interface look professional and clean.
        
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(center_container)
        hbox.addStretch()
        
        wrapper_layout.addStretch()
        wrapper_layout.addLayout(hbox)
        wrapper_layout.addStretch()
        
        layout.addWidget(wrapper)
        
        self.password_value = ""

    def press_key(self, char):
        if len(self.password_value) < 6:
            self.password_value += char
            self.pin_display.setText(self.password_value)
            
    def clear_keys(self):
        self.password_value = ""
        self.pin_display.setText("")
        
    def submit_login(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='app_password'")
        stored_password = c.fetchone()[0]
        conn.close()
        
        if self.password_value == stored_password:
            global CURRENT_USER_AUTHENTICATED
            CURRENT_USER_AUTHENTICATED = True
            self.stacked_widget.setCurrentIndex(1)
        else:
            QMessageBox.critical(self, "خطأ بالرقم السري", "الرقم السري الذي أدخلته غير صحيح. أعد المحاولة.")
            self.clear_keys()

    def toggle_active_orders_sidebar(self):
        is_visible = self.left_col.isVisible()
        self.left_col.setVisible(not is_visible)
        if not is_visible:
            self.btn_toggle_orders.setStyleSheet("QPushButton { background-color: #8cffa7; color: #0e1e1d; border: 2px solid #8cffa7; border-radius: 4px; padding: 6px 12px; font-weight: bold; }")
        else:
            self.btn_toggle_orders.setStyleSheet("QPushButton { background-color: rgba(255, 255, 255, 0.04); color: white; border: 1px solid #263434; border-radius: 4px; padding: 6px 12px; font-weight: bold; }")

    # ── SHIFT SYSTEM CONTROLS ──
    def ensure_active_shift(self):
        global ACTIVE_SHIFT_ID
        conn = database.get_connection()
        c = conn.cursor()
        
        # Check if there is an open shift
        c.execute("SELECT id, expected_cash FROM shifts WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1")
        open_shift = c.fetchone()
        
        if open_shift:
            ACTIVE_SHIFT_ID = open_shift[0]
            self.lbl_drawer_cash.setText(f"الدرج: {open_shift[1]:,.2f} ج.م")
        else:
            # Create a new shift automatically
            opened_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO shifts (opened_at, expected_cash, actual_cash) VALUES (?, 0.0, 0.0)", (opened_time,))
            conn.commit()
            ACTIVE_SHIFT_ID = c.lastrowid
            self.lbl_drawer_cash.setText("الدرج: 0.00 ج.م")
            
        conn.close()
        
    def close_shift_and_drawer(self):
        # Verification password 456
        dlg = PasswordVerificationDialog("إغلاق وردية شيفت المبيعات والدرج", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            sdlg = ShiftClosingDialog(self)
            if sdlg.exec() == QDialog.DialogCode.Accepted:
                QMessageBox.information(self, "تم الإغلاق", "تم إغلاق الوردية بنجاح. سيتم فتح وردية جديدة تلقائياً للطلبات التالية.")
                self.ensure_active_shift()

    def manually_edit_drawer_cash(self):
        """Allow manager to manually set the drawer cash balance."""
        dlg = PasswordVerificationDialog("تعديل رصيد الدرج النقدي يدوياً", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Read current balance
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT expected_cash FROM shifts WHERE id=?", (ACTIVE_SHIFT_ID,))
        row = c.fetchone()
        conn.close()
        current_val = row[0] if row else 0.0

        # Simple input dialog
        input_dlg = QDialog(self)
        input_dlg.setWindowTitle("تعديل الدرج")
        input_dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        input_dlg.setFixedSize(320, 160)
        input_dlg.setStyleSheet(STYLE_SHEET)

        lyt = QVBoxLayout(input_dlg)
        lyt.setContentsMargins(20, 20, 20, 20)
        lyt.setSpacing(12)

        lbl = QLabel(f"أدخل المبلغ الجديد للدرج (الحالي: {current_val:,.2f} ج.م):", input_dlg)
        lbl.setWordWrap(True)
        lyt.addWidget(lbl)

        amount_input = QLineEdit(input_dlg)
        amount_input.setPlaceholderText("0.00")
        amount_input.setText(f"{current_val:.2f}")
        amount_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt.addWidget(amount_input)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("إلغاء", input_dlg)
        btn_cancel.setObjectName("BtnDark")
        btn_cancel.clicked.connect(input_dlg.reject)
        btn_save = QPushButton("💾 حفظ", input_dlg)
        btn_save.clicked.connect(input_dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        lyt.addLayout(btn_row)

        if input_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            new_val = float(amount_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "خطأ", "القيمة المدخلة غير صالحة.")
            return

        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE shifts SET expected_cash = ? WHERE id=?", (new_val, ACTIVE_SHIFT_ID))
        conn.commit()
        conn.close()

        self.lbl_drawer_cash.setText(f"الدرج: {new_val:,.2f} ج.م")
        QMessageBox.information(self, "تم التحديث", f"تم تحديث رصيد الدرج إلى {new_val:,.2f} ج.م بنجاح.")

    def delete_order_action(self, order_id):
        """Delete an order after manager confirmation, deducting cash from drawer if applicable."""
        dlg = PasswordVerificationDialog(f"حذف الطلب #{order_id} من السيستم", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        confirm = QMessageBox.question(
            self, "تأكيد الحذف النهائي",
            f"هتحذف الطلب #{order_id} نهائياً من السيستم.\n"
            "لو كان الطلب تم تحصيله كاش، هيتشال من رصيد الدرج تلقائياً.\n\n"
            "مؤكد؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        conn = database.get_connection()
        c = conn.cursor()

        # Fetch order payment info to deduct from drawer if cash
        c.execute("SELECT payment_method, cash_paid, status FROM orders WHERE id=?", (order_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            QMessageBox.warning(self, "خطأ", f"لم يتم العثور على الطلب #{order_id}.")
            return

        pay_method, cash_paid, status = row
        cash_paid = cash_paid or 0.0

        # Only deduct from drawer if it was a completed cash order
        if pay_method == "CASH" and cash_paid > 0 and status == "COMPLETED":
            c.execute(
                "UPDATE shifts SET expected_cash = MAX(0.0, expected_cash - ?) WHERE id=?",
                (cash_paid, ACTIVE_SHIFT_ID)
            )

        # Delete order items then order
        c.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        c.execute("DELETE FROM orders WHERE id=?", (order_id,))

        conn.commit()
        conn.close()

        # Refresh drawer display
        self.ensure_active_shift()
        # Refresh pending orders sidebar
        self.load_pending_delivery_orders()

        QMessageBox.information(self, "تم الحذف", f"تم حذف الطلب #{order_id} بنجاح.")

    # ── MENU & CATEGORY LOADS ──
    def load_categories(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name FROM categories ORDER BY sort_order ASC")
        cats = c.fetchall()
        conn.close()
        
        # Clear sidebar container first
        for i in reversed(range(self.cat_sidebar_layout.count())):
            widget = self.cat_sidebar_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        # All items tab
        btn_all = QPushButton("🗂️ الكل", self.categories_container)
        btn_all.setObjectName("CategoryTab")
        btn_all.setCheckable(True)
        btn_all.setChecked(True)
        btn_all.setFixedHeight(48)
        btn_all.setStyleSheet("""
            QPushButton {
                text-align: right; font-weight: bold; font-size: 14px; background-color: rgba(255,255,255,0.03); border: 2px solid #263434; color: white; border-radius: 8px; padding-right: 12px;
            }
            QPushButton:checked { background-color: #8cffa7; color: #0e1e1d; border-color: #8cffa7; }
        """)
        btn_all.clicked.connect(lambda: self.filter_category(None, btn_all))
        self.cat_sidebar_layout.addWidget(btn_all)
        self.category_buttons = [btn_all]
        
        # Emojis for categories
        cat_emojis = {
            "وجبات بروست": "🍗",
            "سندوتشات بروست": "🌯",
            "وجبات ستربس": "🍤",
            "قطع بروست": "📦",
            "برجر بروست": "🍔",
            "ريزو وبطاطس": "🍚",
            "وجبات ميكس": "🍲",
            "إضافات بروست": "🍟"
        }
        
        for cat_id, name in cats:
            emoji = cat_emojis.get(name, "🍽️")
            btn = QPushButton(f"{emoji} {name}", self.categories_container)
            btn.setObjectName("CategoryTab")
            btn.setCheckable(True)
            btn.setFixedHeight(48)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: right; font-weight: bold; font-size: 14px; background-color: rgba(255,255,255,0.03); border: 2px solid #263434; color: white; border-radius: 8px; padding-right: 12px;
                }
                QPushButton:checked { background-color: #8cffa7; color: #0e1e1d; border-color: #8cffa7; }
            """)
            btn.clicked.connect(lambda checked, idx=cat_id, b=btn: self.filter_category(idx, b))
            self.cat_sidebar_layout.addWidget(btn)
            self.category_buttons.append(btn)
            
        self.cat_sidebar_layout.addStretch()

    def filter_category(self, cat_id, clicked_btn):
        for btn in self.category_buttons:
            btn.setChecked(btn == clicked_btn)
            
        self.load_menu_items(cat_id)

    def load_popular_items(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, base_price FROM menu_items WHERE is_available=1 AND is_popular=1 LIMIT 5")
        populars = c.fetchall()
        conn.close()
        
        # Clear layout
        for i in reversed(range(self.pop_buttons_layout.count())):
            widget = self.pop_buttons_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        for item_id, name, price in populars:
            btn = QPushButton(f"⭐ {name}", self.pop_buttons_widget)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 168, 246, 0.05); color: #ffa8f6; border: 1px solid rgba(255, 168, 246, 0.3); border-radius: 20px; font-size: 11px; padding: 4px 10px; font-weight: bold;
                }
                QPushButton:hover { background: rgba(255, 168, 246, 0.15); border-color: #ffa8f6; }
            """)
            btn.clicked.connect(lambda checked, idx=item_id, n=name, p=price: self.add_to_cart(idx, n, p))
            self.pop_buttons_layout.addWidget(btn)

    def load_menu_items(self, cat_id):
        # Clear grid layout
        for i in reversed(range(self.menu_grid.count())):
            item = self.menu_grid.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        conn = database.get_connection()
        c = conn.cursor()
        if cat_id:
            c.execute("SELECT id, name, base_price, is_available FROM menu_items WHERE category_id=?", (cat_id,))
        else:
            c.execute("SELECT id, name, base_price, is_available FROM menu_items")
        items = c.fetchall()
        
        # Pre-query sizes for all items
        item_sizes = {}
        for it in items:
            c.execute("SELECT name, price_offset FROM menu_item_sizes WHERE item_id=?", (it[0],))
            sizes = c.fetchall()
            if sizes:
                item_sizes[it[0]] = sizes
                
        conn.close()
        
        row, col = 0, 0
        cols_count = 3
        
        for item_id, name, price, available in items:
            card = QFrame(self.menu_container)
            card.setObjectName("MenuItemCard")
            # Fixed size: compact — no large empty gaps
            card.setFixedHeight(105 if item_id not in item_sizes else 110)
            
            # Card interior layout — tight margins, no stretches
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(4)
            
            # Food category emojis
            emoji = "🍗"
            if "سندوتش" in name or "برجر" in name:
                emoji = "🍔" if "برجر" in name else "🌯"
            elif "ريزو" in name:
                emoji = "🍚"
            elif "ستربس" in name:
                emoji = "🍤"
            elif "بيبسي" in name or "كانز" in name:
                emoji = "🥤"
            elif "بطاطس" in name:
                emoji = "🍟"
            elif "صوص" in name or "تومية" in name:
                emoji = "🍯"
                
            lbl_name = QLabel(f"{emoji} {name}", card)
            lbl_name.setWordWrap(True)
            lbl_name.setStyleSheet("font-weight: 800; font-size: 12px; color: white; background: transparent; border: none;")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            lbl_name.setFixedHeight(40)
            card_layout.addWidget(lbl_name)
            
            # Add direct adding sizes or single click add — NO stretch before
            if item_id in item_sizes:
                sizes_layout = QHBoxLayout()
                sizes_layout.setSpacing(4)
                sizes_layout.setContentsMargins(0, 0, 0, 0)
                for size_name, offset in item_sizes[item_id]:
                    final_price = price + offset
                    btn_size = QPushButton(f"{size_name}  {final_price:.0f}ج", card)
                    btn_size.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(140, 255, 167, 0.06); color: #8cffa7;
                            border: 1px solid rgba(140, 255, 167, 0.25); border-radius: 6px;
                            padding: 3px 4px; font-size: 11px; font-weight: bold;
                        }
                        QPushButton:hover { background-color: #8cffa7; color: #0e1e1d; border-color: #8cffa7; }
                        QPushButton:pressed { background-color: #6ee68c; }
                    """)
                    btn_size.clicked.connect(lambda checked, idx=item_id, n=name, s=size_name, p=final_price: self.add_to_cart_direct(idx, n, s, p))
                    sizes_layout.addWidget(btn_size)
                card_layout.addLayout(sizes_layout)
            else:
                btn_add = QPushButton(f"+ إضافة  {price:.0f} ج.م", card)
                btn_add.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(168, 222, 255, 0.06); color: #a8deff;
                        border: 1px solid rgba(168, 222, 255, 0.25); border-radius: 6px;
                        padding: 5px; font-size: 12px; font-weight: bold;
                    }
                    QPushButton:hover { background-color: #a8deff; color: #0e1e1d; border-color: #a8deff; }
                    QPushButton:pressed { background-color: #7fcbf5; }
                """)
                btn_add.clicked.connect(lambda checked, idx=item_id, n=name, p=price: self.add_to_cart_direct(idx, n, "عادي", p))
                card_layout.addWidget(btn_add)
                
            # Temporary Disable view
            if not available:
                card.setEnabled(False)
                card.setStyleSheet("QFrame#MenuItemCard { background-color: rgba(255, 168, 246, 0.05); border: 1px dashed rgba(255, 168, 246, 0.3); }")
                for i in range(card_layout.count()):
                    w = card_layout.itemAt(i)
                    if w and w.widget():
                        w.widget().setEnabled(False)
                        if isinstance(w.widget(), QPushButton):
                            w.widget().setText("خلصان ⚠️")
                            
            self.menu_grid.addWidget(card, row, col)
            
            col += 1
            if col >= cols_count:
                col = 0
                row += 1

    # ── CART MANAGEMENT ──
    def add_to_cart_direct(self, item_id, name, size_name, price):
        # Search if identical item with size/extras exists in cart to increase quantity
        found = False
        for cart_item in self.cart_items:
            if (cart_item["id"] == item_id and 
                cart_item["size"] == size_name and 
                not cart_item["extras"]): # only combine if no custom extras added yet
                cart_item["qty"] += 1
                found = True
                break
                
        if not found:
            self.cart_items.append({
                "id": item_id,
                "name": name,
                "size": size_name,
                "extras": {}, # empty by default
                "base_price": price,
                "price": price,
                "qty": 1,
                "spicy": False
            })
            
        self.refresh_cart_display()

    def add_to_cart(self, item_id, name, price):
        # Open details picker for custom size / extras
        dlg = ItemDetailsPickerDialog(item_id, name, price, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            qty = dlg.quantity
            size = dlg.selected_size
            offset = dlg.size_offset
            extras = dlg.selected_extras
            
            # Calculate item checkout price
            single_price = price + offset + sum(extras.values())
            
            # Search if identical item with size/extras exists in cart to increase quantity
            found = False
            for cart_item in self.cart_items:
                if (cart_item["id"] == item_id and
                    cart_item["size"] == size and
                    cart_item["extras"] == extras):
                    cart_item["qty"] += qty
                    found = True
                    break
                    
            if not found:
                self.cart_items.append({
                    "id": item_id,
                    "name": name,
                    "size": size,
                    "extras": extras,
                    "base_price": price,
                    "price": single_price,
                    "qty": qty
                })
                
            self.refresh_cart_display()

    def edit_cart_item_options(self, idx):
        item = self.cart_items[idx]
        dlg = ItemDetailsPickerDialog(item["id"], item["name"], item["base_price"], self)
        # Pre-select choices
        dlg.prefill_selections(item["size"], item["qty"], item["extras"])
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            item["qty"] = dlg.quantity
            item["size"] = dlg.selected_size
            item["extras"] = dlg.selected_extras
            item["price"] = item["base_price"] + dlg.size_offset + sum(dlg.selected_extras.values())
            self.refresh_cart_display()

    def refresh_cart_display(self):
        # Clear cart layout — remove ALL items including stretches
        while self.cart_layout.count():
            child = self.cart_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        subtotal = 0.0
        
        for idx, item in enumerate(self.cart_items):
            row = QFrame(self.cart_container)
            row.setObjectName("CartItemRow")
            row.setFixedHeight(42)
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(8, 4, 8, 4)
            r_layout.setSpacing(6)
            
            # Item name + size label (stretches to fill space)
            extras_txt = ", ".join(item["extras"].keys())
            is_spicy = item.get("spicy", False)
            display_txt = f"<b>{item['name']}</b>"
            if is_spicy:
                display_txt += " <span style='color:#ff5050;font-size:13px;'>🌶️</span>"
            if item['size'] and item['size'] != 'عادي':
                display_txt += f" <span style='color:#a8deff;font-size:11px;'>({item['size']})</span>"
            if extras_txt:
                display_txt += f" <span style='color:#ffd9a8;font-size:10px;'>+{extras_txt}</span>"
            
            info_lbl = QLabel(display_txt, row)
            info_lbl.setWordWrap(False)
            info_lbl.setStyleSheet("border: none; background: transparent; font-size: 12px;")
            r_layout.addWidget(info_lbl, stretch=1)
            
            # Qty: [−] N [+] — compact inline
            captured_idx = idx
            btn_m = QPushButton("−", row)
            btn_m.setFixedSize(22, 22)
            btn_m.setStyleSheet("QPushButton { background: rgba(255,168,246,0.1); color: #ffa8f6; border: 1px solid rgba(255,168,246,0.3); border-radius: 4px; font-weight: bold; font-size: 13px; padding: 0; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; }")
            btn_m.clicked.connect(lambda checked, i=captured_idx: self.adjust_cart_qty(i, -1))
            
            lbl_q = QLabel(str(item["qty"]), row)
            lbl_q.setFixedWidth(24)
            lbl_q.setStyleSheet("font-weight: 900; font-size: 14px; border: none; background: transparent; color: white;")
            lbl_q.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            btn_p = QPushButton("+", row)
            btn_p.setFixedSize(22, 22)
            btn_p.setStyleSheet("QPushButton { background: rgba(140,255,167,0.1); color: #8cffa7; border: 1px solid rgba(140,255,167,0.3); border-radius: 4px; font-weight: bold; font-size: 13px; padding: 0; } QPushButton:hover { background: #8cffa7; color: #0e1e1d; }")
            btn_p.clicked.connect(lambda checked, i=captured_idx: self.adjust_cart_qty(i, 1))
            
            r_layout.addWidget(btn_m)
            r_layout.addWidget(lbl_q)
            r_layout.addWidget(btn_p)
            
            # Spicy toggle button
            btn_spicy = QPushButton("🌶️", row)
            btn_spicy.setFixedSize(22, 22)
            btn_spicy.setCheckable(True)
            btn_spicy.setChecked(is_spicy)
            if is_spicy:
                btn_spicy.setStyleSheet("QPushButton { background: rgba(255,80,80,0.25); border: 1px solid #ff5050; border-radius: 4px; font-size: 12px; padding: 0; } QPushButton:hover { background: rgba(255,80,80,0.5); }")
            else:
                btn_spicy.setStyleSheet("QPushButton { background: transparent; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; font-size: 12px; padding: 0; opacity: 0.35; } QPushButton:hover { border-color: #ff5050; background: rgba(255,80,80,0.1); }")
            btn_spicy.clicked.connect(lambda checked, i=captured_idx: self.toggle_spicy(i))
            r_layout.addWidget(btn_spicy)
            
            # Line total price
            item_total = item["price"] * item["qty"]
            subtotal += item_total
            lbl_prc = QLabel(f"{item_total:.0f}", row)
            lbl_prc.setFixedWidth(52)
            lbl_prc.setStyleSheet("font-family: monospace; font-weight: bold; font-size: 13px; color: #8cffa7; border: none; background: transparent;")
            lbl_prc.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            r_layout.addWidget(lbl_prc)
            
            # Delete button
            btn_del = QPushButton("✕", row)
            btn_del.setFixedSize(20, 20)
            btn_del.setStyleSheet("QPushButton { color: rgba(255,168,246,0.5); background: transparent; border: none; font-size: 12px; padding: 0; } QPushButton:hover { color: #ffa8f6; }")
            btn_del.clicked.connect(lambda checked, i=captured_idx: self.remove_cart_item(i))
            r_layout.addWidget(btn_del)
            
            self.cart_layout.addWidget(row)
            
        self.cart_layout.addStretch()
        
        # Calculate subtotal / grand totals
        self.lbl_subtotal.setText(f"{subtotal:,.2f} ج.م")
        
        delivery_fee = 15.0 if self.active_channel == "delivery" else 0.0
        self.delivery_charge_row.setVisible(self.active_channel == "delivery")
        
        grand_total = self.get_grand_total()
        self.lbl_grand_total.setText(f"{grand_total:,.2f} ج.م")
        
        self.calculate_change_due()

    def adjust_cart_qty(self, idx, delta):
        new_qty = self.cart_items[idx]["qty"] + delta
        if new_qty >= 1:
            self.cart_items[idx]["qty"] = new_qty
        else:
            self.cart_items.pop(idx)
        self.refresh_cart_display()

    def remove_cart_item(self, idx):
        # Requires manager confirmation password 456
        dlg = PasswordVerificationDialog("مسح صنف من السلة البيعية", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cart_items.pop(idx)
            self.refresh_cart_display()

    def toggle_spicy(self, idx):
        self.cart_items[idx]["spicy"] = not self.cart_items[idx].get("spicy", False)
        self.refresh_cart_display()

    def confirm_clear_cart(self):
        if not self.cart_items:
            return
        dlg = PasswordVerificationDialog("مسح وإفراغ السلة بالكامل", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cart_items = []
            self.refresh_cart_display()

    # ── CUSTOMER AND LOOKUPS ──
    def switch_channel(self, mode):
        self.active_channel = mode
        self.btn_chan_cashier.setProperty("active", mode == "cashier")
        self.btn_chan_delivery.setProperty("active", mode == "delivery")
        
        # Toggle widgets stylings
        self.btn_chan_cashier.setStyle(self.btn_chan_cashier.style())
        self.btn_chan_delivery.setStyle(self.btn_chan_delivery.style())
        
        # Always show lookup box, toggle fields
        self.cust_lookup_box.setVisible(True)
        
        if mode == "cashier":
            # Cashier: name required, phone optional, hide address
            self.cust_phone_input.setVisible(True)
            self.cust_phone_input.setPlaceholderText("رقم الموبايل (اختياري)...")
            self.cust_name_input.setPlaceholderText("اسم العميل (إجباري)...")
            self.cust_addr_input.setVisible(False)
            self.btn_repeat_order.setVisible(False)
        else:
            # Delivery: full form
            self.cust_phone_input.setVisible(True)
            self.cust_phone_input.setPlaceholderText("رقم موبايل العميل...")
            self.cust_name_input.setPlaceholderText("اسم العميل...")
            self.cust_addr_input.setVisible(True)
        
        # Change theme highlighting
        if mode == "cashier":
            self.lbl_grand_total.setStyleSheet("font-size: 24px; font-weight: 800; color: #8cffa7;")
            self.btn_submit_order.setStyleSheet("QPushButton { background-color: #dcffe4; } QPushButton:hover { background-color: #8cffa7; }")
        else:
            self.lbl_grand_total.setStyleSheet("font-size: 24px; font-weight: 800; color: #a8deff;")
            self.btn_submit_order.setStyleSheet("QPushButton { background-color: #b0e3ff; } QPushButton:hover { background-color: #a8deff; }")
            
        self.refresh_cart_display()

    def handle_phone_changed(self):
        phone = self.cust_phone_input.text().strip()
        if len(phone) == 11:
            self.trigger_customer_search()

    def trigger_customer_search(self):
        phone = self.cust_phone_input.text().strip()
        if not phone:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, address FROM customers WHERE phone=?", (phone,))
        cust = c.fetchone()
        
        if cust:
            self.current_customer_id = cust[0]
            self.current_customer_name = cust[1]
            self.current_customer_address = cust[2]
            
            self.cust_name_input.setText(self.current_customer_name)
            self.cust_addr_input.setText(self.current_customer_address)
            
            # Show repeat previous order button
            self.btn_repeat_order.setVisible(True)
        else:
            self.current_customer_id = None
            self.btn_repeat_order.setVisible(False)
            
        conn.close()

    def handle_customer_details_edited(self):
        # Keep local fields updated as user types
        self.current_customer_name = self.cust_name_input.text().strip()
        self.current_customer_address = self.cust_addr_input.toPlainText().strip()

    def repeat_last_order_for_customer(self):
        if not self.current_customer_id:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        # Find last completed order for customer
        c.execute("""
            SELECT id FROM orders 
            WHERE customer_id=? AND status='COMPLETED' 
            ORDER BY id DESC LIMIT 1
        """, (self.current_customer_id,))
        last_order = c.fetchone()
        
        if not last_order:
            QMessageBox.information(self, "لا يوجد سجل", "لا توجد فواتير سابقة مسجلة لهذا العميل لتكرارها.")
            conn.close()
            return
            
        order_id = last_order[0]
        c.execute("""
            SELECT menu_item_id, size_name, quantity, price, extras_json
            FROM order_items WHERE order_id=?
        """, (order_id,))
        order_items = c.fetchall()
        
        self.cart_items = []
        for item_id, size_name, qty, price, extras_json in order_items:
            c.execute("SELECT name FROM menu_items WHERE id=?", (item_id,))
            name = c.fetchone()[0]
            
            extras = {}
            if extras_json:
                extras_list = json.loads(extras_json)
                if isinstance(extras_list, dict):
                    extras = extras_list
                elif isinstance(extras_list, list):
                    # Fallback list of dicts conversion
                    for ex in extras_list:
                        extras[ex["name"]] = ex["price"]
                        
            self.cart_items.append({
                "id": item_id,
                "name": name,
                "size": size_name,
                "extras": extras,
                "base_price": price - sum(extras.values()), # estimate base
                "price": price,
                "qty": qty
            })
            
        conn.close()
        self.refresh_cart_display()
        QMessageBox.information(self, "تكرار الفاتورة", "تم ملء السلة بمحتويات طلب العميل السابق بنجاح.")

    # ── CHECKOUT AND PRINTING ──
    def switch_payment_method(self, method):
        self.payment_method = method
        self.btn_pay_cash.setChecked(method == "cash")
        self.btn_pay_visa.setChecked(method == "visa")
        self.btn_pay_wallet.setChecked(method == "wallet")
        
        self.cash_calc_widget.setVisible(method == "cash")
        self.calculate_change_due()

    def apply_cash_preset(self, val):
        self.paid_input.setText(str(val))
        self.calculate_change_due()

    def apply_exact_cash(self):
        grand_total = self.get_grand_total()
        self.paid_input.setText(f"{grand_total:.2f}")
        self.calculate_change_due()

    def calculate_change_due(self):
        grand_total = self.get_grand_total()
        
        try:
            paid = float(self.paid_input.text())
        except ValueError:
            paid = 0.0
            
        change = paid - grand_total
        if change >= 0:
            self.lbl_change_title.setText("الباقي للعميل:")
            self.lbl_change_due.setText(f"{change:,.2f} ج.م")
            self.lbl_change_due.setStyleSheet("font-weight: bold; color: #8cffa7;")
        else:
            remaining = abs(change)
            self.lbl_change_title.setText("⚠️ متبقي على العميل:")
            self.lbl_change_due.setText(f"{remaining:,.2f} ج.م")
            self.lbl_change_due.setStyleSheet("font-weight: bold; color: #ffa8f6;")

    def get_grand_total(self):
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items)
        delivery_fee = 15.0 if self.active_channel == "delivery" else 0.0
        try:
            discount = float(self.discount_input.text()) if hasattr(self, 'discount_input') and self.discount_input.text().strip() else 0.0
        except ValueError:
            discount = 0.0
        return max(0.0, subtotal + delivery_fee - discount)

    def checkout_order(self):
        if not self.cart_items:
            QMessageBox.warning(self, "السلة فارغة", "يرجى إضافة وجبات إلى السلة لإتمام الدفع.")
            return
            
        # Warning alert if delivery address details are missing
        if self.active_channel == "delivery":
            phone = self.cust_phone_input.text().strip()
            name = self.cust_name_input.text().strip()
            address = self.cust_addr_input.toPlainText().strip()
            
            if not phone or not name or not address:
                QMessageBox.critical(self, "تحذير: عنوان ناقص", "لا يمكن إتمام الطلب كدليفري بدون تسجيل هاتف العميل واسمه وعنوان التوصيل بالتفصيل!")
                return
        else:
            # Cashier/Takeaway: name required
            name = self.cust_name_input.text().strip()
            if not name:
                QMessageBox.critical(self, "اسم العميل مطلوب", "يرجى كتابة اسم العميل لإتمام الطلب في الصالة / التيك أواي.")
                return
                
        # Confirm details and prices before printing
        confirm_dlg = QMessageBox.question(
            self, "تأكيد الطلب", 
            f"هل تود تأكيد ترحيل الفاتورة بقيمة إجمالية {self.get_grand_total():,.2f} ج.م؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm_dlg != QMessageBox.StandardButton.Yes:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        
        # 1. Customer registration or update
        customer_id = None
        name = self.cust_name_input.text().strip()
        phone = self.cust_phone_input.text().strip()
        
        if self.active_channel == "delivery":
            address = self.cust_addr_input.toPlainText().strip()
            
            # Check if exists by phone
            c.execute("SELECT id FROM customers WHERE phone=?", (phone,))
            exist = c.fetchone()
            if exist:
                customer_id = exist[0]
                c.execute("UPDATE customers SET name=?, address=? WHERE id=?", (name, address, customer_id))
            else:
                c.execute("INSERT INTO customers (phone, name, address) VALUES (?, ?, ?)", (phone, name, address))
                customer_id = c.lastrowid
        else:
            # Cashier/Takeaway: save customer with name (phone optional)
            if phone:
                c.execute("SELECT id FROM customers WHERE phone=?", (phone,))
                exist = c.fetchone()
                if exist:
                    customer_id = exist[0]
                    c.execute("UPDATE customers SET name=? WHERE id=?", (name, customer_id))
                else:
                    c.execute("INSERT INTO customers (phone, name, address) VALUES (?, ?, ?)", (phone, name, ""))
                    customer_id = c.lastrowid
            else:
                # No phone, just save with name
                c.execute("INSERT INTO customers (phone, name, address) VALUES (?, ?, ?)", (None, name, ""))
                customer_id = c.lastrowid
                
        # 2. Insert Order
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items)
        delivery_fee = 15.0 if self.active_channel == "delivery" else 0.0
        try:
            discount = float(self.discount_input.text()) if hasattr(self, 'discount_input') and self.discount_input.text().strip() else 0.0
        except ValueError:
            discount = 0.0
        grand_total = max(0.0, subtotal + delivery_fee - discount)
        
        paid = 0.0
        change = 0.0
        if self.payment_method == "cash":
            try:
                paid = float(self.paid_input.text())
            except ValueError:
                paid = 0.0
            change = max(0.0, paid - grand_total)
            
        # Cashier orders also start as PENDING until cashier marks done
        status = "PENDING"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""
            INSERT INTO orders (customer_id, channel, payment_method, subtotal, delivery_fee, discount, total, cash_paid, change_due, status, shift_id, created_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (customer_id, self.active_channel.upper(), self.payment_method.upper(), subtotal, delivery_fee, discount, grand_total, paid, change, status, ACTIVE_SHIFT_ID, now_str, None))
        
        order_id = c.lastrowid
        
        # 3. Insert Items
        for item in self.cart_items:
            item_extras = dict(item["extras"])
            if item.get("spicy", False):
                item_extras["__spicy__"] = True
            c.execute("""
                INSERT INTO order_items (order_id, menu_item_id, size_name, quantity, price, extras_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order_id, item["id"], item["size"], item["qty"], item["price"], json.dumps(item_extras)))
            
        # Shift drawer update deferred to order completion
        conn.commit()
        conn.close()
        
        # 5. Generate Receipt contents
        cashier_receipt = self.generate_receipt_text(order_id, "نسخة الكاشير")
        kitchen_receipt = self.generate_receipt_text(order_id, "نسخة المطبخ")
        
        # Open Printer preview simulation dialog
        psim = ReceiptSimDialog(order_id, cashier_receipt, kitchen_receipt, self)
        psim.exec()
        
        # Clear cart and refresh drawer widgets
        self.cart_items = []
        self.cust_phone_input.clear()
        self.cust_name_input.clear()
        self.cust_addr_input.clear()
        if hasattr(self, 'discount_input'):
            self.discount_input.clear()
        self.btn_repeat_order.setVisible(False)
        self.refresh_cart_display()
        self.ensure_active_shift()
        self.load_pending_delivery_orders()

    def generate_receipt_text(self, order_id, copy_title):
        conn = database.get_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT o.id, o.channel, o.payment_method, o.subtotal, o.delivery_fee, COALESCE(o.discount, 0.0), o.total, o.created_at,
                   cust.name, cust.phone, cust.address, o.cash_paid, o.change_due
            FROM orders o
            LEFT JOIN customers cust ON o.customer_id = cust.id
            WHERE o.id=?
        """, (order_id,))
        o_data = c.fetchone()
        
        c.execute("""
            SELECT m.name, oi.size_name, oi.quantity, oi.price, oi.extras_json
            FROM order_items oi
            JOIN menu_items m ON oi.menu_item_id = m.id
            WHERE oi.order_id=?
        """, (order_id,))
        o_items = c.fetchall()
        
        conn.close()
        
        if not o_data:
            return ""
            
        # Build layout receipt string
        lines = []
        lines.append("="*30)
        lines.append("          مطعم بروست          ")
        lines.append(f"         {copy_title}         ")
        lines.append("="*30)
        lines.append(f"رقم الفاتورة: #{o_data[0]}")
        lines.append(f"تاريخ الطلب: {o_data[7]}")
        lines.append(f"قناة الطلب: {'دليفري توصيل' if o_data[1]=='DELIVERY' else 'صالة تيك أواي'}")
        lines.append(f"طريقة الدفع: {'نقدي كاش' if o_data[2]=='CASH' else ('فيزا كارت' if o_data[2]=='VISA' else 'محفظة ذكية')}")
        lines.append("-"*30)
        
        if o_data[1] == 'DELIVERY':
            lines.append(f"العميل: {o_data[8]}")
            lines.append(f"تليفون: {o_data[9]}")
            lines.append(f"العنوان: {o_data[10]}")
            lines.append("-"*30)
            
        lines.append("الطلبات:")
        for name, size, qty, price, ext_json in o_items:
            # Parse extras_json — may have spicy flag embedded
            spicy_flag = False
            ext_dict = {}
            if ext_json:
                try:
                    parsed = json.loads(ext_json)
                    if isinstance(parsed, dict):
                        spicy_flag = parsed.pop("__spicy__", False)
                        ext_dict = parsed
                    else:
                        ext_dict = {}
                except Exception:
                    pass
            
            spicy_label = " 🌶️ حار" if spicy_flag else ""
            lines.append(f"- {name} ({size}) x{qty}{spicy_label}")
            ext_names = ", ".join(ext_dict.keys())
            if ext_names:
                lines.append(f"  إضافات: {ext_names}")
            lines.append(f"  السعر: {price*qty:.2f} ج.م")
            
        lines.append("="*30)
        lines.append(f"المجموع الفرعي: {o_data[3]:.2f} ج.م")
        if o_data[1] == 'DELIVERY':
            lines.append(f"عمولة الطيار: {o_data[4]:.2f} ج.م")
            
        discount = o_data[5]
        if discount > 0.0:
            lines.append(f"الخصم المطبق: -{discount:.2f} ج.م")
        
        total = o_data[6]
        lines.append(f"الإجمالي الكلي: {total:.2f} ج.م")
        
        # Display payments and debts dynamically
        pay_method = o_data[2]
        cash_paid = o_data[11] if o_data[11] is not None else 0.0
        change_due = o_data[12] if o_data[12] is not None else 0.0
        
        if pay_method == 'CASH':
            if cash_paid < total:
                remaining = total - cash_paid
                lines.append(f"المبلغ المدفوع: {cash_paid:.2f} ج.م")
                lines.append(f"⚠️ المتبقي (أجل): {remaining:.2f} ج.م")
            else:
                lines.append(f"المبلغ المدفوع: {cash_paid:.2f} ج.م")
                lines.append(f"المتبقي (الباقي): {change_due:.2f} ج.م")
                
        lines.append("="*30)
        lines.append("     شكراً لكم وزيارة سعيدة!     ")
        lines.append("="*30)
        
        return "\n".join(lines)

    # ── PENDING / DISPATCH CHANNELS ──
    def load_pending_delivery_orders(self):
        # Clean clear using deleteLater
        while self.orders_layout.count():
            child = self.orders_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT o.id, o.total, o.created_at, COALESCE(cust.name, 'صالة'), 
                   COALESCE(cust.address, ''), o.status, COALESCE(d.name, ''), o.channel,
                   o.cash_paid, o.payment_method
            FROM orders o
            LEFT JOIN customers cust ON o.customer_id = cust.id
            LEFT JOIN drivers d ON o.driver_id = d.id
            WHERE o.status IN ('PENDING', 'DISPATCHED')
            ORDER BY o.created_at ASC
        """)
        pending = c.fetchall()
        conn.close()
        
        count = len(pending)
        
        # Update count badge
        if hasattr(self, 'orders_count_badge'):
            self.orders_count_badge.setText(str(count))
            if count > 0:
                self.orders_count_badge.setStyleSheet(
                    "background: rgba(140,255,167,0.15); color: #8cffa7; "
                    "border: 1px solid rgba(140,255,167,0.4); border-radius: 10px; "
                    "padding: 1px 10px; font-weight: bold; font-size: 12px;"
                )
            else:
                self.orders_count_badge.setStyleSheet(
                    "background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.3); "
                    "border: 1px solid #263434; border-radius: 10px; "
                    "padding: 1px 10px; font-weight: bold; font-size: 12px;"
                )
        
        # Update header toggle button
        if hasattr(self, 'btn_toggle_orders'):
            self.btn_toggle_orders.setText(f"الطلبات 🔔 ({count})")
            if count > 0:
                self.btn_toggle_orders.setStyleSheet("QPushButton { background-color: rgba(140,255,167,0.12); color: #8cffa7; border: 1px solid rgba(140,255,167,0.4); border-radius: 4px; padding: 6px 12px; font-weight: bold; }")
            else:
                self.btn_toggle_orders.setStyleSheet("QPushButton { background-color: rgba(255,255,255,0.04); color: rgba(255,255,255,0.5); border: 1px solid #263434; border-radius: 4px; padding: 6px 12px; font-weight: bold; }")
        
        # Empty state
        if not pending:
            empty = QLabel("✓  لا توجد طلبات جارية", self.orders_container)
            empty.setStyleSheet(
                "color: rgba(255,255,255,0.18); font-size: 12px; font-weight: bold; "
                "border: 1px dashed rgba(255,255,255,0.08); border-radius: 8px; "
                "background: rgba(255,255,255,0.01); padding: 18px;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.orders_layout.addWidget(empty)
            return
        
        for o_id, total, created_at, cust_name, address, status, d_name, channel, cash_paid, pay_method in pending:
            is_delivery = (channel == 'DELIVERY')
            delta = datetime.now() - datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
            mins_waiting = int(delta.total_seconds() / 60)
            is_late = mins_waiting >= 15
            is_critical = mins_waiting >= 40

            card = QFrame(self.orders_container)
            card.setObjectName("PendingOrderCard")
            card.setProperty("delivery", is_delivery)
            if is_critical:
                card.setProperty("critical", True)
            elif is_late:
                card.setProperty("warning", True)
            card.setStyleSheet(STYLE_SHEET)

            c_lyt = QVBoxLayout(card)
            c_lyt.setContentsMargins(12, 10, 12, 10)
            c_lyt.setSpacing(6)

            # Row 1: icon + order id + timer badge
            r1 = QHBoxLayout()
            icon = "🛵" if is_delivery else "🏠"
            lbl_id = QLabel(f"{icon}  #{o_id}", card)
            lbl_id.setStyleSheet("font-weight: 900; font-size: 13px; color: white; border: none; background: transparent;")
            r1.addWidget(lbl_id)
            r1.addStretch()
            
            if is_critical:
                timer_color = "#ff5050"
                timer_bg = "rgba(255,80,80,0.12)"
            elif is_late:
                timer_color = "#ffa8f6"
                timer_bg = "rgba(255,168,246,0.12)"
            else:
                timer_color = "#a8deff"
                timer_bg = "rgba(168,222,255,0.08)"
                
            lbl_time = QLabel(f"⏱ {mins_waiting}د", card)
            lbl_time.setStyleSheet(
                f"background: {timer_bg}; color: {timer_color}; "
                f"border: 1px solid {timer_color}; border-radius: 4px; "
                f"padding: 1px 8px; font-size: 11px; font-weight: bold;"
            )
            r1.addWidget(lbl_time)
            c_lyt.addLayout(r1)

            # Row 2: Customer name + price / unpaid debt check
            r2 = QHBoxLayout()
            lbl_cust = QLabel(cust_name, card)
            lbl_cust.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.55); border: none; background: transparent;")
            r2.addWidget(lbl_cust)
            r2.addStretch()
            
            # Check if paid less in CASH
            cash_val = cash_paid if cash_paid is not None else 0.0
            if pay_method == 'CASH' and cash_val < total:
                remaining = total - cash_val
                lbl_price = QLabel(f"دفع: {cash_val:.0f} / متبقي: {remaining:.0f} ج", card)
                lbl_price.setStyleSheet("font-weight: bold; font-size: 11px; color: #ffa8f6; border: none; background: transparent;")
            else:
                lbl_price = QLabel(f"{total:.0f} ج", card)
                lbl_price.setStyleSheet("font-weight: 900; font-size: 13px; color: #8cffa7; border: none; background: transparent;")
                
            r2.addWidget(lbl_price)
            c_lyt.addLayout(r2)

            # Row 3: action buttons
            r3 = QHBoxLayout()
            r3.setSpacing(6)

            if is_delivery and status == 'PENDING':
                btn_dispatch = QPushButton("🛵 تكليف", card)
                btn_dispatch.setFixedHeight(28)
                btn_dispatch.setStyleSheet(
                    "QPushButton { background: rgba(168,222,255,0.08); color: #a8deff; "
                    "border: 1px solid rgba(168,222,255,0.3); border-radius: 6px; "
                    "font-size: 11px; font-weight: bold; padding: 0 10px; } "
                    "QPushButton:hover { background: #a8deff; color: #0e1e1d; }"
                )
                btn_dispatch.clicked.connect(lambda checked, idx=o_id: self.dispatch_delivery_order(idx))
                r3.addWidget(btn_dispatch)
            elif is_delivery and d_name:
                lbl_driver = QLabel(f"🛵 {d_name}", card)
                lbl_driver.setStyleSheet("font-size: 10px; color: rgba(255,255,255,0.35); border: none; background: transparent;")
                r3.addWidget(lbl_driver)

            r3.addStretch()

            btn_edit = QPushButton("📝 تعديل", card)
            btn_edit.setFixedHeight(28)
            btn_edit.setFixedWidth(64)
            btn_edit.setStyleSheet(
                "QPushButton { background: rgba(255,217,168,0.08); color: #ffd9a8; "
                "border: 1px solid rgba(255,217,168,0.3); border-radius: 6px; "
                "font-size: 11px; font-weight: bold; padding: 0px 4px; } "
                "QPushButton:hover { background: #ffd9a8; color: #0e1e1d; }"
            )
            btn_edit.clicked.connect(lambda checked, idx=o_id: self.open_edit_order_dialog(idx))
            r3.addWidget(btn_edit)

            btn_done = QPushButton("✓ خلص", card)
            btn_done.setFixedHeight(28)
            btn_done.setFixedWidth(72)
            btn_done.setStyleSheet(
                "QPushButton { background: rgba(140,255,167,0.08); color: #8cffa7; "
                "border: 1px solid rgba(140,255,167,0.3); border-radius: 6px; "
                "font-size: 11px; font-weight: bold; padding: 0px 6px; } "
                "QPushButton:hover { background: #8cffa7; color: #0e1e1d; }"
            )
            btn_done.clicked.connect(lambda checked, i=o_id, ch=channel: self.complete_order(i, ch))
            r3.addWidget(btn_done)
            c_lyt.addLayout(r3)

            self.orders_layout.addWidget(card)

    def refresh_pending_orders_timers(self):
        # Periodically refresh delay timers
        self.load_pending_delivery_orders()
        # Update sidebar time label
        if hasattr(self, "lbl_sidebar_time"):
            self.lbl_sidebar_time.setText(datetime.now().strftime("%I:%M %p"))

    def dispatch_delivery_order(self, order_id):
        # Open driver picker selector
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name FROM drivers WHERE is_active=1")
        drivers = c.fetchall()
        conn.close()
        
        if not drivers:
            QMessageBox.warning(self, "لا يوجد طيارين", "يرجى تسجيل طيارين توصيل متاحين بالنظام أولاً لتوزيع الأوردرات.")
            return
            
        # Quick input dialog select driver
        items = [f"{d[1]} (id: {d[0]})" for d in drivers]
        d_picker = QDialog(self)
        d_picker.setWindowTitle("اختر الطيار لتسليمه الأوردر")
        d_picker.setFixedSize(300, 160)
        d_picker.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        
        lyt = QVBoxLayout(d_picker)
        lyt.addWidget(QLabel("اختر طيار التوصيل لتوصيل الطلب:", d_picker))
        
        cb = QComboBox(d_picker)
        cb.addItems(items)
        lyt.addWidget(cb)
        
        btn_lyt = QHBoxLayout()
        btn_ok = QPushButton("تأكيد التكليف", d_picker)
        btn_ok.clicked.connect(d_picker.accept)
        btn_no = QPushButton("تراجع", d_picker)
        btn_no.setObjectName("BtnDark")
        btn_no.clicked.connect(d_picker.reject)
        
        btn_lyt.addWidget(btn_no)
        btn_lyt.addWidget(btn_ok)
        lyt.addLayout(btn_lyt)
        
        if d_picker.exec() == QDialog.DialogCode.Accepted:
            selected_txt = cb.currentText()
            driver_id = int(selected_txt.split("id: ")[1].replace(")", ""))
            
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("UPDATE orders SET driver_id=?, status='DISPATCHED' WHERE id=?", (driver_id, order_id))
            conn.commit()
            conn.close()
            
            self.load_pending_delivery_orders()

    def complete_order(self, order_id, channel):
        """Mark any order (cashier or delivery) as COMPLETED and update shift cash."""
        is_delivery = (channel == 'DELIVERY')
        msg = "هل عاد الطيار وتم التسليم والتحصيل؟" if is_delivery else "تأكيد إنهاء الأوردر وإيصال الطلب للعميل؟"
        confirm = QMessageBox.question(
            self, "تأكيد إنهاء الأوردر", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT total, payment_method, cash_paid FROM orders WHERE id=?", (order_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        total, method, cash_paid = row
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE orders SET status='COMPLETED', closed_at=? WHERE id=?", (now_str, order_id))
        
        # Update shift expected_cash only for cash payments (adding actual cash paid)
        if method == "CASH":
            actual_cash = cash_paid if cash_paid is not None else total
            c.execute("UPDATE shifts SET expected_cash = MAX(0.0, expected_cash + ?) WHERE id=?", (actual_cash, ACTIVE_SHIFT_ID))
            
        conn.commit()
        conn.close()
        
        self.load_pending_delivery_orders()
        self.ensure_active_shift()

    def complete_delivery_order(self, order_id):
        """Legacy alias kept for backwards compatibility."""
        self.complete_order(order_id, 'DELIVERY')

    def open_edit_order_dialog(self, order_id):
        dlg = OrderEditDialog(order_id, self)
        dlg.exec()



    # ── MANAGERS / REPORTS OVERLAYS ──
    def open_menu_management(self):
        # Verification password 456
        dlg = PasswordVerificationDialog("لوحة إدارة وتعديل المنيو", self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            mdlg = MenuAdminDialog(self)
            if mdlg.exec() == QDialog.DialogCode.Accepted:
                self.load_categories()
                self.load_popular_items()
                self.load_menu_items(None)

    def open_drivers_management(self):
        dlg = DriversAdminDialog(self)
        dlg.exec()
        self.load_pending_delivery_orders()

    def open_reports_dialog(self):
        dlg = ReportsDialog(self)
        dlg.exec()

    def trigger_manual_backup(self):
        success, path = database.run_backup()
        if success:
            QMessageBox.information(self, "نسخة احتياطية ناجحة", f"تم حفظ نسخة احتياطية من قواعد البيانات بنجاح على المسار:\n{path}")
        else:
            QMessageBox.critical(self, "خطأ بالنسخ الاحتياطي", f"حدث خطأ أثناء حفظ النسخة الاحتياطية:\n{path}")

    def run_automated_daily_backup(self):
        # Check if database has been backed up today
        backup_flag_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_backup_date")
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        should_backup = True
        if os.path.exists(backup_flag_file):
            with open(backup_flag_file, "r") as f:
                last_date = f.read().strip()
                if last_date == today_str:
                    should_backup = False
                    
        if should_backup:
            success, path = database.run_backup()
            if success:
                print(f"[Backup Engine] Automated daily backup saved at: {path}")
                with open(backup_flag_file, "w") as f:
                    f.write(today_str)

    def toggle_printer_connection_sim(self):
        global PRINTER_ONLINE
        PRINTER_ONLINE = not PRINTER_ONLINE
        if PRINTER_ONLINE:
            self.btn_printer_status.setText("طابعة المطبخ والكاشير: متصلة")
            self.btn_printer_status.setStyleSheet("QPushButton { background-color: rgba(140, 255, 167, 0.05); color: #8cffa7; border: 1px solid rgba(140, 255, 167, 0.2); border-radius: 4px; padding: 6px 12px; font-weight: bold; }")
        else:
            self.btn_printer_status.setText("طابعة المطبخ والكاشير: معطلة ⚠️")
            self.btn_printer_status.setStyleSheet("QPushButton { background-color: rgba(255, 168, 246, 0.05); color: #ffa8f6; border: 1px solid rgba(255, 168, 246, 0.2); border-radius: 4px; padding: 6px 12px; font-weight: bold; }")



class OrderEditDialog(QDialog):
    """Premium dialog to edit pending/active orders, add/remove items, adjust payments, and sync accounts."""
    def __init__(self, order_id, parent=None):
        super().__init__(parent)
        self.order_id = order_id
        self.parent_dashboard = parent
        self.setWindowTitle(f"تعديل الطلب #{self.order_id}")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(500, 600)
        self.setStyleSheet(STYLE_SHEET)
        
        self.items = []
        self.delivery_fee = 0.0
        self.payment_method = "CASH"
        self.customer_name = ""
        self.customer_phone = ""
        
        self.init_ui()
        self.load_order_details()
        self.load_menu_items()
        self.recalculate()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Header block
        header = QHBoxLayout()
        title = QLabel(f"✏️ تعديل محتويات الطلب #{self.order_id}", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffd9a8; border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(26, 26)
        btn_close.setStyleSheet("QPushButton { background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.6); border: 1px solid #263434; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; border-color: #ffa8f6; }")
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        layout.addLayout(header)
        
        self.lbl_cust_info = QLabel("👤 جاري تحميل تفاصيل العميل...", self)
        self.lbl_cust_info.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px; font-weight: bold; padding-bottom: 2px;")
        layout.addWidget(self.lbl_cust_info)
        
        # Add new item form row
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        
        self.cb_menu = QComboBox(self)
        self.cb_menu.setStyleSheet("QComboBox { background: #040808; border: 1px solid #263434; border-radius: 6px; color: white; padding: 4px 8px; font-size: 12px; } QComboBox::drop-down { border: none; }")
        add_row.addWidget(self.cb_menu, stretch=3)
        
        self.cb_size = QComboBox(self)
        self.cb_size.addItems(["عادي", "كبير", "عائلي"])
        self.cb_size.setStyleSheet("QComboBox { background: #040808; border: 1px solid #263434; border-radius: 6px; color: white; padding: 4px 8px; font-size: 12px; } QComboBox::drop-down { border: none; }")
        add_row.addWidget(self.cb_size, stretch=1)
        
        btn_add = QPushButton("➕ إضافة وجبة", self)
        btn_add.setFixedHeight(28)
        btn_add.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8cffa7, stop:1 #8cffa7); color: #0e1e1d; border: none; border-radius: 6px; font-size: 11px; font-weight: bold; padding: 0 10px; } QPushButton:hover { background: white; }")
        btn_add.clicked.connect(self.add_selected_item)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)
        
        # Items Scroll List
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: rgba(255,255,255,0.01); border: 1px solid #263434; border-radius: 8px;")
        
        self.scroll_widget = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_widget)
        self.items_layout.setContentsMargins(8, 8, 8, 8)
        self.items_layout.setSpacing(6)
        
        self.scroll.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll)
        
        # Calculations Panel
        calc_box = QFrame(self)
        calc_box.setStyleSheet("background: rgba(255,255,255,0.01); border: 1px solid #263434; border-radius: 8px; padding: 8px;")
        calc_lyt = QVBoxLayout(calc_box)
        calc_lyt.setSpacing(6)
        
        r_sub = QHBoxLayout()
        r_sub.addWidget(QLabel("المجموع الفرعي:", calc_box))
        r_sub.addStretch()
        self.lbl_subtotal = QLabel("0.00 ج", calc_box)
        self.lbl_subtotal.setStyleSheet("color: white; font-weight: bold;")
        r_sub.addWidget(self.lbl_subtotal)
        calc_lyt.addLayout(r_sub)
        
        r_discount = QHBoxLayout()
        r_discount.addWidget(QLabel("خصم مطبق (ج.م):", calc_box))
        r_discount.addStretch()
        self.txt_discount = QLineEdit(calc_box)
        self.txt_discount.setFixedWidth(90)
        self.txt_discount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_discount.setStyleSheet("QLineEdit { background: #040808; border: 1px solid #263434; border-radius: 4px; color: white; padding: 3px; font-weight: bold; } QLineEdit:focus { border-color: #ffd9a8; }")
        self.txt_discount.textChanged.connect(self.recalculate)
        r_discount.addWidget(self.txt_discount)
        calc_lyt.addLayout(r_discount)
        
        r_grand = QHBoxLayout()
        r_grand.addWidget(QLabel("الإجمالي الكلي (شامل التوصيل):", calc_box))
        r_grand.addStretch()
        self.lbl_grand = QLabel("0.00 ج", calc_box)
        self.lbl_grand.setStyleSheet("color: #8cffa7; font-weight: bold; font-size: 14px;")
        r_grand.addWidget(self.lbl_grand)
        calc_lyt.addLayout(r_grand)
        
        # Separator
        sep = QFrame(calc_box)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #263434; max-height: 1px; border: none;")
        calc_lyt.addWidget(sep)
        
        # Paid input & balance
        pay_row = QHBoxLayout()
        pay_row.addWidget(QLabel("💵 الكاش المدفوع حالياً:", calc_box))
        self.txt_paid = QLineEdit(calc_box)
        self.txt_paid.setFixedWidth(90)
        self.txt_paid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_paid.setStyleSheet("QLineEdit { background: #040808; border: 1px solid #263434; border-radius: 4px; color: white; padding: 3px; font-weight: bold; } QLineEdit:focus { border-color: #ffd9a8; }")
        self.txt_paid.textChanged.connect(self.recalculate)
        pay_row.addWidget(self.txt_paid)
        calc_lyt.addLayout(pay_row)
        
        change_row = QHBoxLayout()
        self.lbl_change_title = QLabel("الباقي للعميل:", calc_box)
        change_row.addWidget(self.lbl_change_title)
        change_row.addStretch()
        self.lbl_change_due = QLabel("0.00 ج", calc_box)
        self.lbl_change_due.setStyleSheet("color: #8cffa7; font-weight: bold;")
        change_row.addWidget(self.lbl_change_due)
        calc_lyt.addLayout(change_row)
        
        layout.addWidget(calc_box)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_cancel = QPushButton("تراجع وإلغاء", self)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet("QPushButton { background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.7); border: 1px solid #263434; border-radius: 6px; font-size: 12px; font-weight: bold; } QPushButton:hover { background: rgba(255,255,255,0.06); color: white; }")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("💾 حفظ وإعادة الطباعة", self)
        self.btn_save.setFixedHeight(36)
        self.btn_save.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffd9a8, stop:1 #ffd9a8); color: #0e1e1d; border: none; border-radius: 6px; font-size: 12px; font-weight: bold; } QPushButton:hover { background: white; color: #0e1e1d; }")
        self.btn_save.clicked.connect(self.save_changes)
        
        btn_layout.addWidget(btn_cancel, stretch=1)
        btn_layout.addWidget(self.btn_save, stretch=2)
        layout.addLayout(btn_layout)
        
    def load_order_details(self):
        conn = database.get_connection()
        c = conn.cursor()
        
        # Load order fields
        c.execute("""
            SELECT o.delivery_fee, o.payment_method, o.cash_paid, o.change_due, cust.name, cust.phone, COALESCE(o.discount, 0.0)
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
            
            self.lbl_cust_info.setText(f"👤 العميل: {self.customer_name} | 💳 الدفع: {'كاش نقدي' if self.payment_method=='CASH' else 'مدفوعات إلكترونية'}")
            self.txt_paid.setText(f"{self.cash_paid:.2f}")
            self.txt_discount.setText(f"{discount_val:.2f}")
            
        # Load items
        c.execute("""
            SELECT menu_item_id, m.name, oi.size_name, oi.quantity, oi.price, oi.extras_json
            FROM order_items oi
            JOIN menu_items m ON oi.menu_item_id = m.id
            WHERE oi.order_id=?
        """, (self.order_id,))
        items_data = c.fetchall()
        for m_id, name, size, qty, price, ext_json in items_data:
            extras = {}
            if ext_json:
                try:
                    extras = json.loads(ext_json)
                except:
                    pass
            self.items.append({
                "id": m_id,
                "name": name,
                "size": size,
                "qty": qty,
                "price": price,
                "extras": extras
            })
            
        conn.close()
        self.refresh_items_display()
        
    def load_menu_items(self):
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, base_price FROM menu_items ORDER BY name ASC")
        self.menu_items = c.fetchall()
        conn.close()
        
        self.cb_menu.clear()
        for m_id, name, price in self.menu_items:
            self.cb_menu.addItem(f"{name} ({price:.0f} ج)", (m_id, name, price))
            
    def add_selected_item(self):
        idx = self.cb_menu.currentIndex()
        if idx < 0:
            return
        m_id, name, price = self.cb_menu.itemData(idx)
        size = self.cb_size.currentText()
        
        # Check size offset from DB
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT price_offset FROM menu_item_sizes WHERE item_id=? AND name=?", (m_id, size))
        offset_row = c.fetchone()
        conn.close()
        
        offset = offset_row[0] if offset_row else 0.0
        final_price = price + offset
        
        # Check if exists
        for item in self.items:
            if item["id"] == m_id and item["size"] == size:
                item["qty"] += 1
                self.refresh_items_display()
                self.recalculate()
                return
                
        self.items.append({
            "id": m_id,
            "name": name,
            "size": size,
            "qty": 1,
            "price": final_price,
            "extras": {}
        })
        self.refresh_items_display()
        self.recalculate()
        
    def refresh_items_display(self):
        # Clear items layout
        while self.items_layout.count():
            child = self.items_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        for index, item in enumerate(self.items):
            row = QFrame(self.scroll_widget)
            row.setObjectName("ItemRow")
            row.setStyleSheet("""
                QFrame#ItemRow {
                    background: rgba(255, 255, 255, 0.02);
                    border: 1px solid #263434;
                    border-radius: 6px;
                }
            """)
            r_lyt = QHBoxLayout(row)
            r_lyt.setContentsMargins(8, 4, 8, 4)
            r_lyt.setSpacing(6)
            
            lbl_name = QLabel(f"{item['name']} ({item['size']})", row)
            lbl_name.setStyleSheet("color: white; font-weight: bold; font-size: 11px; border: none; background: transparent;")
            r_lyt.addWidget(lbl_name, stretch=3)
            
            btn_minus = QPushButton("-", row)
            btn_minus.setFixedSize(18, 18)
            btn_minus.setStyleSheet("QPushButton { background: rgba(255,255,255,0.04); color: white; border: 1px solid #263434; border-radius: 4px; font-weight: bold; font-size: 10px; } QPushButton:hover { background: #ffa8f6; color: #0e1e1d; }")
            btn_minus.clicked.connect(lambda checked, idx=index: self.adjust_qty(idx, -1))
            r_lyt.addWidget(btn_minus)
            
            lbl_qty = QLabel(str(item["qty"]), row)
            lbl_qty.setStyleSheet("color: #ffd9a8; font-weight: bold; font-size: 11px; border: none; background: transparent;")
            lbl_qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_qty.setFixedWidth(16)
            r_lyt.addWidget(lbl_qty)
            
            btn_plus = QPushButton("+", row)
            btn_plus.setFixedSize(18, 18)
            btn_plus.setStyleSheet("QPushButton { background: rgba(255,255,255,0.04); color: white; border: 1px solid #263434; border-radius: 4px; font-weight: bold; font-size: 10px; } QPushButton:hover { background: #8cffa7; color: #0e1e1d; }")
            btn_plus.clicked.connect(lambda checked, idx=index: self.adjust_qty(idx, 1))
            r_lyt.addWidget(btn_plus)
            
            lbl_price = QLabel(f"{item['price'] * item['qty']:.0f} ج", row)
            lbl_price.setStyleSheet("color: #8cffa7; font-weight: bold; font-size: 11px; border: none; background: transparent;")
            lbl_price.setFixedWidth(40)
            lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            r_lyt.addWidget(lbl_price)
            
            btn_del = QPushButton("✕", row)
            btn_del.setFixedSize(18, 18)
            btn_del.setStyleSheet("QPushButton { background: rgba(255,80,80,0.1); color: #ff6b6b; border: 1px solid rgba(255,80,80,0.3); border-radius: 4px; font-weight: bold; font-size: 9px; } QPushButton:hover { background: #ff5050; color: white; }")
            btn_del.clicked.connect(lambda checked, idx=index: self.remove_item(idx))
            r_lyt.addWidget(btn_del)
            
            self.items_layout.addWidget(row)
            
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
            discount = float(self.txt_discount.text().strip()) if hasattr(self, 'txt_discount') and self.txt_discount.text().strip() else 0.0
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
            self.lbl_change_due.setStyleSheet("color: #8cffa7; font-weight: bold; border: none; background: transparent;")
        else:
            remaining = abs(change)
            self.lbl_change_title.setText("⚠️ متبقي للتحصيل:")
            self.lbl_change_due.setText(f"{remaining:.2f} ج")
            self.lbl_change_due.setStyleSheet("color: #ffa8f6; font-weight: bold; border: none; background: transparent;")
            
    def save_changes(self):
        if not self.items:
            QMessageBox.warning(self, "طلب فارغ", "لا يمكن حفظ الطلب وهو فارغ تماماً. يرجى إضافة وجبات أو إلغاء التعديل.")
            return
            
        subtotal = sum(item["price"] * item["qty"] for item in self.items)
        try:
            discount = float(self.txt_discount.text().strip()) if hasattr(self, 'txt_discount') and self.txt_discount.text().strip() else 0.0
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
        
        # 1. Update order
        c.execute("""
            UPDATE orders
            SET subtotal = ?,
                discount = ?,
                total = ?,
                cash_paid = ?,
                change_due = ?
            WHERE id = ?
        """, (subtotal, discount, grand_total, paid, change, self.order_id))
        
        # 2. Delete old order items
        c.execute("DELETE FROM order_items WHERE order_id = ?", (self.order_id,))
        
        # 3. Insert new order items
        for item in self.items:
            c.execute("""
                INSERT INTO order_items (order_id, menu_item_id, size_name, quantity, price, extras_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (self.order_id, item["id"], item["size"], item["qty"], item["price"], json.dumps(item["extras"])))
            
        conn.commit()
        conn.close()
        
        # 4. Generate new receipts and simulate printing preview
        if self.parent_dashboard:
            cashier_receipt = self.parent_dashboard.generate_receipt_text(self.order_id, "نسخة الكاشير (معدلة)")
            kitchen_receipt = self.parent_dashboard.generate_receipt_text(self.order_id, "نسخة المطبخ (معدلة)")
            
            # Refresh pending list in dashboard
            self.parent_dashboard.load_pending_delivery_orders()
            
            # Launch simulated printing preview dialog
            psim = ReceiptSimDialog(self.order_id, cashier_receipt, kitchen_receipt, self.parent_dashboard)
            psim.exec()
            
        self.accept()


if __name__ == "__main__":
    database.init_db()
    app = QApplication(sys.argv)
    
    dashboard = MainPOSDashboard()
    dashboard.showMaximized()
    sys.exit(app.exec())
