# -*- coding: utf-8 -*-
"""Broost POS - Main POS Dashboard Window"""
import os
import sys
import json
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QPoint, QEvent, QProcess
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame, QDialog,
    QComboBox, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QStackedWidget, QTabWidget, QApplication, QTextEdit, QSizePolicy,
    QSplitter, QGraphicsBlurEffect, QFileDialog
)
from PyQt6.QtGui import QIcon, QFont, QPixmap

import database
from styles import STYLE_SHEET
from core import config
from core.printing import print_text_to_printer
from core.display_text import pos_text
from core.time_utils import elapsed_minutes
from widgets.title_bar import CustomTitleBar
from dialogs.login import LoginDialog, PasswordVerificationDialog
from dialogs.item_picker import ItemDetailsPickerDialog
from dialogs.drivers import DriversAdminDialog
from dialogs.menu_admin import MenuAdminDialog
from dialogs.reports import ReportsDialog
from dialogs.shift import ShiftClosingDialog, ShiftSummaryReportDialog
from dialogs.receipt import ReceiptSimDialog
from dialogs.order_edit import OrderEditDialog
from dialogs.online_order import OnlineOrderAlertDialog, CustomerCancelledOrderAlertDialog
from dialogs.daily_offers import DailyOffersDialog
from core.online_sync import OnlineSyncManager


class ExitOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("خيارات الخروج والوردية")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(450, 290)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border: 2px solid #0078d4;
                border-radius: 12px;
            }
        """)
        self.choice = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Title
        title_lbl = QLabel("🚪 خيارات الخروج والوردية", self)
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold; color: #0078d4; border: none; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(title_lbl)

        # Info text
        info_lbl = QLabel("ما الإجراء الذي تود القيام به؟\nيمكنك تسوية الدرج وإغلاق الوردية الحالية بالكامل، أو مجرد تسجيل الخروج لتبديل الكاشير مع بقاء الوردية مفتوحة.", self)
        info_lbl.setStyleSheet("font-size: 13px; color: #374151; border: none; background: transparent; line-height: 140%;")
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        layout.addSpacing(10)

        # Buttons stacked vertically
        btn_close = QPushButton("🔒 تسوية وإغلاق الوردية الحالية", self)
        btn_close.setFixedHeight(44)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; color: white;
                border: none; border-radius: 8px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #106ebe; }
            QPushButton:pressed { background-color: #005a9e; }
        """)
        btn_close.clicked.connect(self.select_close)
        layout.addWidget(btn_close)

        btn_logout = QPushButton("👤 تسجيل خروج فقط (تبديل كاشير)", self)
        btn_logout.setFixedHeight(44)
        btn_logout.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6; color: #1f2937;
                border: 1px solid #d1d5db; border-radius: 8px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #e5e7eb; }
            QPushButton:pressed { background-color: #d1d5db; }
        """)
        btn_logout.clicked.connect(self.select_logout)
        layout.addWidget(btn_logout)

        btn_cancel = QPushButton("تراجع وإلغاء", self)
        btn_cancel.setFixedHeight(38)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #4b5563;
                border: 1px solid #e5e7eb; border-radius: 8px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #f9fafb; color: #111827; }
        """)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    def select_close(self):
        self.choice = 'close'
        self.accept()

    def select_logout(self):
        self.choice = 'logout'
        self.accept()


class DialogBackdrop(QWidget):
    """Semi-transparent black overlay backdrop that dims the main window when a dialog is opened."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.45);")  # beautiful 45% dark overlay
        self.show()
        # Install event filter to track parent resizing
        parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)

# Save original QDialog.exec
original_qdialog_exec = QDialog.exec

def custom_qdialog_exec(self):
    # Find MainPOSDashboard parent if exists
    parent = self.parent()
    main_window = None
    while parent:
        if parent.__class__.__name__ == "MainPOSDashboard":
            main_window = parent
            break
        parent = parent.parent()
        
    if main_window and hasattr(main_window, 'main_widget'):
        # 1. Apply graphics blur effect to central widget
        blur = QGraphicsBlurEffect(main_window)
        blur.setBlurRadius(15)
        main_window.main_widget.setGraphicsEffect(blur)
        
        # 2. Show backdrop overlay
        backdrop = DialogBackdrop(main_window)
        
        try:
            res = original_qdialog_exec(self)
        finally:
            # 3. Clean up
            backdrop.deleteLater()
            main_window.main_widget.setGraphicsEffect(None)
        return res
    else:
        return original_qdialog_exec(self)

QDialog.exec = custom_qdialog_exec

class VirtualKeyboardWidget(QWidget):
    closed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_input = None
        self.mode = "text" # "text" or "number"
        self.lang = "ar" # "ar" or "en"
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setObjectName("VirtualKeyboard")
        self.setStyleSheet("""
            QWidget#VirtualKeyboard {
                background-color: #d1d5db; /* iOS light gray keyboard background */
                border: 1px solid #b5b5b5;
                border-radius: 10px;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(8)
        
        # Header (Close / Title)
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(6, 2, 6, 2)
        
        self.lbl_title = QLabel("لوحة المفاتيح الذكية ⌨️", self)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #4b5563; border: none; background: transparent;")
        self.header_layout.addWidget(self.lbl_title)
        
        self.header_layout.addStretch()
        
        self.btn_close = QPushButton("تم ✓", self)
        self.btn_close.setFixedHeight(28)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #0a84ff; color: white;
                border: none; border-radius: 5px;
                padding: 0 14px; font-weight: bold; font-size: 12px;
                border-bottom: 1.5px solid #0056b3;
            }
            QPushButton:hover { background-color: #0070e0; }
            QPushButton:pressed { background-color: #0056b3; }
        """)
        self.btn_close.clicked.connect(self.close_keyboard)
        self.header_layout.addWidget(self.btn_close)
        
        self.main_layout.addLayout(self.header_layout)
        
        self.modes_stack = QStackedWidget(self)
        self.modes_stack.setStyleSheet("background: transparent; border: none;")
        
        # Page 0: Text layout
        self.text_widget = QWidget(self)
        self.text_widget.setStyleSheet("border: none; background: transparent;")
        self.text_layout = QVBoxLayout(self.text_widget)
        self.text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_layout.setSpacing(6)
        
        self.modes_stack.addWidget(self.text_widget)
        
        # Page 1: Number Pad
        self.number_widget = QWidget(self)
        self.number_widget.setStyleSheet("border: none; background: transparent;")
        self.number_layout = QVBoxLayout(self.number_widget)
        self.number_layout.setContentsMargins(0, 0, 0, 0)
        self.number_layout.setSpacing(0)
        
        self.modes_stack.addWidget(self.number_widget)
        
        self.main_layout.addWidget(self.modes_stack)
        
        self.build_text_keyboard()
        self.build_number_keypad()
        
    def set_target(self, input_field, mode="text"):
        self.target_input = input_field
        self.mode = mode
        if mode == "number":
            self.lbl_title.setText("لوحة الأرقام السريعة 🔢")
            self.modes_stack.setCurrentIndex(1)
        else:
            self.lbl_title.setText("لوحة الحروف الذكية ⌨️")
            self.modes_stack.setCurrentIndex(0)
            self.lang = "ar"
            self.update_text_layout()
            
    def close_keyboard(self):
        if self.target_input:
            self.target_input.clearFocus()
        self.closed.emit()
        
    def key_pressed(self, val):
        if not self.target_input:
            return
            
        if val == "backspace":
            self.target_input.backspace()
        elif val == "space":
            self.target_input.insert(" ")
        elif val == "clear":
            self.target_input.clear()
        elif val == "lang":
            self.lang = "en" if self.lang == "ar" else "ar"
            self.update_text_layout()
        else:
            self.target_input.insert(val)
            
        self.target_input.setFocus()
        
    def get_key_style(self, special=False, done=False):
        if done:
            return """
                QPushButton {
                    background-color: #0a84ff; color: white;
                    border: none; border-radius: 5px;
                    font-weight: bold; font-size: 14px;
                    border-bottom: 1.5px solid #0056b3;
                }
                QPushButton:hover { background-color: #0070e0; }
                QPushButton:pressed { background-color: #0056b3; }
            """
        elif special:
            return """
                QPushButton {
                    background-color: #acb1c1; color: #000000;
                    border: none; border-radius: 5px;
                    font-weight: bold; font-size: 14px;
                    border-bottom: 1.5px solid #8e95a0;
                }
                QPushButton:hover { background-color: #9ba1b1; }
                QPushButton:pressed { background-color: #838896; }
            """
        else:
            return """
                QPushButton {
                    background-color: #ffffff; color: #000000;
                    border: none; border-radius: 5px;
                    font-weight: bold; font-size: 16px;
                    border-bottom: 1.5px solid #acb1b7;
                }
                QPushButton:hover { background-color: #f1f2f6; }
                QPushButton:pressed { background-color: #e1e2e6; }
            """
            
    def build_text_keyboard(self):
        self.update_text_layout()
        
    def update_text_layout(self):
        # Clear existing text layout
        while self.text_layout.count():
            item = self.text_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                item.layout().deleteLater()
            elif item.widget():
                item.widget().deleteLater()
                
        if self.lang == "ar":
            # Standard QWERTY Arabic layout (iOS / PC standard arrangement)
            rows = [
                ['ض', 'ص', 'ث', 'ق', 'ف', 'غ', 'ع', 'ه', 'خ', 'ح', 'ج', 'د'],
                ['ش', 'س', 'ي', 'ب', 'ل', 'ا', 'ت', 'ن', 'م', 'ك', 'ط', 'ذ'],
                ['ئ', 'ء', 'ؤ', 'ر', 'لا', 'ى', 'ة', 'و', 'ز', 'ظ', 'أ', 'إ', 'آ']
            ]
            lang_lbl = "English 🌐"
        else:
            # iOS-inspired English layout rows
            rows = [
                ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
                ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
                ['z', 'x', 'c', 'v', 'b', 'n', 'm']
            ]
            lang_lbl = "عربي 🌐"
            
        for row in rows:
            r_lay = QHBoxLayout()
            r_lay.setSpacing(6)
            for char in row:
                btn = QPushButton(char, self.text_widget)
                btn.setFixedHeight(42)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(self.get_key_style())
                btn.clicked.connect(lambda checked, c=char: self.key_pressed(c))
                r_lay.addWidget(btn)
            self.text_layout.addLayout(r_lay)
            
        # Row 4: Controls (iPhone layout style)
        r_controls = QHBoxLayout()
        r_controls.setSpacing(6)
        
        btn_lang = QPushButton(lang_lbl, self.text_widget)
        btn_lang.setFixedHeight(44)
        btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_lang.setStyleSheet(self.get_key_style(special=True))
        btn_lang.clicked.connect(lambda: self.key_pressed("lang"))
        r_controls.addWidget(btn_lang, stretch=2)
        
        btn_space = QPushButton("مسافة", self.text_widget)
        btn_space.setFixedHeight(44)
        btn_space.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_space.setStyleSheet(self.get_key_style())
        btn_space.clicked.connect(lambda: self.key_pressed("space"))
        r_controls.addWidget(btn_space, stretch=5)
        
        btn_back = QPushButton("⌫", self.text_widget)
        btn_back.setFixedHeight(44)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet(self.get_key_style(special=True))
        btn_back.clicked.connect(lambda: self.key_pressed("backspace"))
        r_controls.addWidget(btn_back, stretch=2)
        
        btn_clear = QPushButton("مسح الكل 🗑", self.text_widget)
        btn_clear.setFixedHeight(44)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet(self.get_key_style(special=True))
        btn_clear.clicked.connect(lambda: self.key_pressed("clear"))
        r_controls.addWidget(btn_clear, stretch=2)
        
        self.text_layout.addLayout(r_controls)
        
    def build_number_keypad(self):
        container = QWidget(self.number_widget)
        container.setObjectName("NumberKeyContainer")
        container.setStyleSheet("background: transparent; border: none;")
        container.setFixedSize(380, 240)
        
        # Center layout
        vbox_center = QVBoxLayout()
        vbox_center.addStretch(1)
        
        hbox = QHBoxLayout()
        hbox.addStretch(1)
        hbox.addWidget(container)
        hbox.addStretch(1)
        
        vbox_center.addLayout(hbox)
        vbox_center.addStretch(1)
        
        self.number_layout.addLayout(vbox_center)
        
        grid = QGridLayout(container)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        
        buttons = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح الكل 🗑', 3, 0), ('0', 3, 1), ('⌫', 3, 2)
        ]
        
        for text, r, c in buttons:
            btn = QPushButton(text, container)
            btn.setFixedSize(115, 48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            if '⌫' in text:
                btn.setStyleSheet(self.get_key_style(special=True))
                btn.clicked.connect(lambda: self.key_pressed("backspace"))
            elif 'مسح الكل' in text:
                btn.setStyleSheet(self.get_key_style(special=True))
                btn.clicked.connect(lambda: self.key_pressed("clear"))
            else:
                btn.setStyleSheet(self.get_key_style())
                btn.clicked.connect(lambda checked, val=text: self.key_pressed(val))
                
            grid.addWidget(btn, r, c)


class MainPOSDashboard(QMainWindow):
    """Main Restaurant checkout dashboard window."""
    
    RESIZE_MARGIN = 8  # pixels from edge to trigger resize cursor
    
    def __init__(self):
        super().__init__()
        # Use native Windows frame to get native title bar, Minimize/Maximize/Close buttons, and snap layout.
        self.setWindowTitle("نظام الكاشير والدليفري")
        
        # Screen resolution check
        screen = QApplication.primaryScreen()
        screen_size = screen.size() if screen else None
        self.is_small_screen = False
        if screen_size and (screen_size.width() <= 1366 or screen_size.height() <= 768):
            self.is_small_screen = True
            
        if self.is_small_screen:
            self.setMinimumSize(1024, 660)
            small_screen_styles = """
                * {
                    font-size: 11px;
                }
                QLabel#GrandTotalLabel {
                    font-size: 18px;
                }
                QPushButton {
                    font-size: 11px;
                    padding: 4px 8px;
                }
                QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                    font-size: 11px;
                    padding: 4px 8px;
                }
                QTabBar::tab {
                    font-size: 11px;
                    padding: 4px 10px;
                }
            """
            self.setStyleSheet(STYLE_SHEET + small_screen_styles)
        else:
            self.setMinimumSize(1024, 700)
            self.setStyleSheet(STYLE_SHEET)
            
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        
        # Resize state
        self._resizing = False
        self._resize_dir = None  # tuple (dx, dy) e.g. (1,0)=right, (0,1)=bottom
        self._resize_start_pos = None
        self._resize_start_geom = None

        # Order cart variables
        self.active_channel = "cashier" # cashier / delivery
        self.payment_method = "cash"
        
        self.current_customer_id = None
        self.current_customer_name = ""
        self.current_customer_address = ""
        
        self.cart_items = [] # list of dicts: {id, name, size, extras: {name: price}, base_price, qty}
        
        self.init_ui()
        self.ensure_active_shift()
        self._current_cat_id = "offers"
        self.load_categories()
        self.load_menu_items("offers")
        self.load_pending_delivery_orders()
        
        # Periodic check for delayed active orders (every 5 seconds)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_pending_orders_timers)
        self.timer.start(5000)
        
        # Automatic backups trigger once a day
        self.run_automated_daily_backup()
        self.backup_timer = QTimer(self)
        self.backup_timer.timeout.connect(self.run_automated_daily_backup)
        self.backup_timer.start(15 * 60 * 1000)  # Re-check every 15 minutes across midnight
        
        # Populate customer phone autocomplete suggestions
        self.update_phone_completer()
        
        # Load persistent printer configurations on startup
        try:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT key, value FROM settings WHERE key IN ('printer_paper_width', 'printer_font_size', 'selected_printer', 'printer_online')")
            db_settings = dict(c.fetchall())
            conn.close()
            
            config.PAPER_WIDTH = int(db_settings.get("printer_paper_width", "80"))
            config.FONT_SIZE_MODE = db_settings.get("printer_font_size", "normal")
            config.SELECTED_PRINTER = db_settings.get("selected_printer", "")
            config.PRINTER_ONLINE = (db_settings.get("printer_online", "1") == "1")
        except Exception as e:
            print("[Startup Config Load] Error loading printer settings:", e)

        # Auto-detect physical printer on startup
        self.auto_detect_printer_on_startup()

        # Website synchronization runs in a background thread and never blocks
        # cashier operations when the internet is unavailable.
        self._online_alert_queue = []
        self._online_alert_open = False
        self.online_sync = OnlineSyncManager(self)
        self.online_sync.connectivity_changed.connect(self.update_online_sync_status)
        self.online_sync.order_received.connect(self.handle_online_order_received)
        self.online_sync.order_updated.connect(self.handle_online_order_updated)
        self.online_sync.menu_applied.connect(self.reload_menu_after_online_sync)
        self.online_sync_timer = QTimer(self)
        self.online_sync_timer.timeout.connect(self.online_sync.poll)
        self.online_sync_timer.start(5000)
        QTimer.singleShot(500, self.online_sync.poll)

    # Custom resize and mouse drag handlers are no longer needed as we use native Windows OS frames now.

    def init_ui(self):
        # Frameless main wrapper
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Custom titlebar is hidden since we are using native Windows Title Bar.
        
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
        header_control_h = 38 if self.is_small_screen else 46
        header_control_w = 104 if self.is_small_screen else 138
        self.header_bar.setFixedHeight(54 if self.is_small_screen else 64)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(8 if self.is_small_screen else 14, 0, 8 if self.is_small_screen else 14, 0)
        header_layout.setSpacing(6 if self.is_small_screen else 8)

        brand_block = QFrame(self.header_bar)
        brand_block.setObjectName("HeaderBrand")
        brand_block.setFixedSize(134 if self.is_small_screen else 164, header_control_h)
        brand_layout = QHBoxLayout(brand_block)
        brand_layout.setContentsMargins(7, 3, 9, 3)
        brand_layout.setSpacing(6)

        brand_icon = QLabel(brand_block)
        icon_size = 31 if self.is_small_screen else 38
        brand_icon.setFixedSize(icon_size, icon_size)
        logo_path = os.path.join(database.BASE_DIR, "logo.png")
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            # The source logo contains a large white artboard. Crop to the real mark
            # before scaling so it stays bold and legible in the compact header.
            crop = logo_pixmap.copy(
                int(logo_pixmap.width() * 0.24),
                int(logo_pixmap.height() * 0.17),
                int(logo_pixmap.width() * 0.52),
                int(logo_pixmap.height() * 0.66),
            )
            brand_icon.setPixmap(
                crop.scaled(
                    icon_size,
                    icon_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(brand_icon)

        brand_name = QLabel("نظام\nالكاشير", brand_block)
        brand_name.setStyleSheet(
            f"font-size: {'11px' if self.is_small_screen else '13px'}; "
            "font-weight: 900; color: #18181b; border: none; background: transparent; letter-spacing: 0.7px;"
        )
        brand_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        brand_layout.addWidget(brand_name, 1)
        header_layout.addWidget(brand_block)
        
        btn_padding = "4px 8px" if self.is_small_screen else "6px 12px"
        btn_font_size = "11px" if self.is_small_screen else "12px"
        
        # Printer Status simulator button
        printer_text = "🖨️ متصلة" if self.is_small_screen else "🖨 الطابعة متصلة"
        self.btn_printer_status = QPushButton(printer_text, self.header_bar)
        self.btn_printer_status.setFixedSize(header_control_w, header_control_h)
        self.btn_printer_status.setStyleSheet(f"QPushButton {{ background-color: #eef9f2; color: #157347; border: 1px solid #a7d9bd; border-radius: 10px; padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }}")
        self.btn_printer_status.clicked.connect(self.open_printer_settings)
        header_layout.addWidget(self.btn_printer_status)

        self.lbl_online_sync = QLabel("● جاري ربط الموقع", self.header_bar)
        self.lbl_online_sync.setObjectName("SyncStatusBadge")
        self.lbl_online_sync.setFixedSize(header_control_w, header_control_h)
        self.lbl_online_sync.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_online_sync)

        # Active Cashier Name Label
        self.lbl_active_cashier = QLabel("👤 —", self.header_bar)
        self.lbl_active_cashier.setFixedSize(header_control_w, header_control_h)
        self.lbl_active_cashier.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_cashier_font = "11px" if self.is_small_screen else "13px"
        lbl_cashier_pad = "4px 8px" if self.is_small_screen else "5px 12px"
        self.lbl_active_cashier.setStyleSheet(f"QLabel {{ background-color: #fff1f2; color: #9f1239; border: 1px solid #fecdd3; border-radius: 10px; padding: {lbl_cashier_pad}; font-weight: bold; font-size: {lbl_cashier_font}; }}")
        header_layout.addWidget(self.lbl_active_cashier)
        
        # Daily offers replaces the old on-screen keyboard toggle.
        self.btn_daily_offers = QPushButton(
            "العروض" if self.is_small_screen else "✨ إدارة العروض",
            self.header_bar,
        )
        self.btn_daily_offers.setObjectName("BtnOffer")
        self.btn_daily_offers.setFixedSize(header_control_w, header_control_h)
        self.btn_daily_offers.clicked.connect(self.open_daily_offers)
        header_layout.addWidget(self.btn_daily_offers)
        
        header_layout.addStretch()
        
        # Action/Admin tools (RTL aligned via layout flow)
        self.btn_toggle_orders = QPushButton("الطلبات الجارية (0)", self.header_bar)
        self.btn_toggle_orders.setFixedSize(header_control_w, header_control_h)
        self.btn_toggle_orders.setToolTip("إخفاء قسم الطلبات الجارية")
        self.btn_toggle_orders.setStyleSheet(f"QPushButton {{ background-color: #ffffff; color: #27272a; border: 1px solid #dedbd7; border-radius: 10px; padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }} QPushButton:hover {{ background-color: #faf5f6; border-color: #e7a4b5; }}")
        self.btn_toggle_orders.clicked.connect(self.toggle_active_orders_sidebar)
        header_layout.addWidget(self.btn_toggle_orders)

        btn_drivers_mgr = QPushButton("🛵 الطيارين", self.header_bar)
        btn_drivers_mgr.setFixedSize(header_control_w, header_control_h)
        btn_drivers_mgr.setObjectName("BtnBlue")
        btn_drivers_mgr.clicked.connect(self.open_drivers_management)
        header_layout.addWidget(btn_drivers_mgr)
        
        btn_menu_mgr = QPushButton("🔧 إدارة المنيو", self.header_bar)
        btn_menu_mgr.setFixedSize(header_control_w, header_control_h)
        btn_menu_mgr.setObjectName("BtnDark")
        btn_menu_mgr.clicked.connect(self.open_menu_management)
        header_layout.addWidget(btn_menu_mgr)
        
        btn_reports = QPushButton("📊 لوحة التقارير", self.header_bar)
        btn_reports.setFixedSize(header_control_w, header_control_h)
        btn_reports.setObjectName("BtnOrange")
        btn_reports.clicked.connect(self.open_reports_dialog)
        header_layout.addWidget(btn_reports)
        
        btn_backup = QPushButton("☁️ نسخة احتياطية", self.header_bar)
        btn_backup.setFixedSize(header_control_w, header_control_h)
        btn_backup.setObjectName("BtnDark")
        btn_backup.clicked.connect(self.trigger_manual_backup)
        header_layout.addWidget(btn_backup)

        btn_close_shift = QPushButton("🚪 إغلاق الوردية", self.header_bar)
        btn_close_shift.setFixedSize(header_control_w, header_control_h)
        btn_close_shift.setObjectName("BtnPink")
        btn_close_shift.clicked.connect(self.close_shift_and_drawer)
        header_layout.addWidget(btn_close_shift)
        
        # User & Settings Profile icons far-right
        btn_user_profile = QPushButton("👤", self.header_bar)
        btn_user_profile.setFixedSize(header_control_h, header_control_h)
        btn_user_profile.setStyleSheet("QPushButton { background-color: #ffffff; color: #27272a; border: 1px solid #dedbd7; border-radius: 10px; font-size: 16px; padding: 0px; } QPushButton:hover { background-color: #fff1f2; border-color: #e7a4b5; }")
        header_layout.addWidget(btn_user_profile)
        
        btn_settings = QPushButton("⚙️", self.header_bar)
        btn_settings.setFixedSize(header_control_h, header_control_h)
        btn_settings.setStyleSheet("QPushButton { background-color: #ffffff; color: #27272a; border: 1px solid #dedbd7; border-radius: 10px; font-size: 16px; padding: 0px; } QPushButton:hover { background-color: #fff1f2; border-color: #e7a4b5; }")
        btn_settings.clicked.connect(self.open_settings_menu)
        header_layout.addWidget(btn_settings)
        
        self.pos_layout.addWidget(self.header_bar)
        
        # [3] POS Grid columns — QSplitter for resizable panels
        self.pos_splitter = QSplitter(Qt.Orientation.Horizontal, self.pos_page)
        self.pos_splitter.setHandleWidth(6)
        self.pos_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #e5e7eb;
                border-radius: 3px;
                margin: 4px 1px;
            }
            QSplitter::handle:hover {
                background: #0078d4;
            }
        """)
        # Keep a dummy widget as parent for children that still use pos_body ref
        pos_body = self.pos_splitter
        
        # Column A: Active Orders Panel (right side - collapsible)
        self.left_col = QFrame(self.pos_page)
        self.left_col.setObjectName("PosPanel")
        self.left_col.setMinimumWidth(135)
        left_layout = QVBoxLayout(self.left_col)
        if self.is_small_screen:
            left_layout.setContentsMargins(6, 6, 6, 6)
            left_layout.setSpacing(6)
        else:
            left_layout.setContentsMargins(12, 12, 12, 12)
            left_layout.setSpacing(10)
        
        # Panel header with live count badge
        left_hdr = QHBoxLayout()
        left_hdr.setSpacing(8)
        
        live_dot = QLabel("●", self.left_col)
        live_dot.setStyleSheet("color: #107c10; font-size: 10px; border: none; background: transparent;")
        left_hdr.addWidget(live_dot)
        
        left_title = QLabel("الطلبات الجارية", self.left_col)
        left_title.setStyleSheet("font-weight: 900; font-size: 14px; color: #1a1a1a; border: none; background: transparent;")
        left_title.setWordWrap(True)
        left_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_hdr.addWidget(left_title)
        left_hdr.addStretch()
        
        self.orders_count_badge = QLabel("0", self.left_col)
        self.orders_count_badge.setStyleSheet(
            "background: #dff6dd; color: #107c10; "
            "border: 1px solid #107c10; border-radius: 10px; "
            "padding: 1px 10px; font-weight: bold; font-size: 12px;"
        )
        self.orders_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_hdr.addWidget(self.orders_count_badge)
        
        left_layout.addLayout(left_hdr)
        
        # Thin separator line
        sep = QFrame(self.left_col)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #e5e5e5; border: none; max-height: 1px;")
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
        self.center_col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_layout = QVBoxLayout(self.center_col)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        # Menu stays visible at all times; the old virtual keyboard page was removed.
        self.menu_page_widget = QWidget(self.center_col)
        center_layout.addWidget(self.menu_page_widget)
        menu_page_layout = QVBoxLayout(self.menu_page_widget)
        menu_page_layout.setContentsMargins(0, 0, 0, 0)
        menu_page_layout.setSpacing(8)
        
        # Grid menu scroll area
        self.scroll_menu = QScrollArea(self.menu_page_widget)
        self.scroll_menu.setWidgetResizable(True)
        self.scroll_menu.setStyleSheet("background: transparent; border: 1px solid #e7e5e4; border-radius: 16px;")
        self.menu_container = QWidget()
        self.menu_container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.menu_grid = QGridLayout(self.menu_container)
        self.menu_grid.setContentsMargins(10, 10, 10, 10)
        self.menu_grid.setSpacing(10)
        self.scroll_menu.setWidget(self.menu_container)
        menu_page_layout.addWidget(self.scroll_menu)
        
        # Column D: Categories Vertical Sidebar (Left side, LTR flow) - 200px width
        self.categories_sidebar = QFrame(pos_body)
        self.categories_sidebar.setObjectName("PosPanel")
        self.categories_sidebar.setMinimumWidth(110 if self.is_small_screen else 150)
        self.categories_sidebar.setMaximumWidth(160 if self.is_small_screen else 220)
        self.categories_sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sidebar_main_layout = QVBoxLayout(self.categories_sidebar)
        if self.is_small_screen:
            sidebar_main_layout.setContentsMargins(6, 6, 6, 6)
            sidebar_main_layout.setSpacing(8)
        else:
            sidebar_main_layout.setContentsMargins(10, 10, 10, 10)
            sidebar_main_layout.setSpacing(12)
        
        # [A] Sidebar Top Drawer & Brand Header
        drawer_row = QHBoxLayout()
        drawer_row.setSpacing(6)
        
        drawer_pad = "4px 6px" if self.is_small_screen else "6px 12px"
        drawer_font = "11px" if self.is_small_screen else "13px"
        self.lbl_drawer_cash = QLabel("الدرج: 0.00 ج.م", self.categories_sidebar)
        self.lbl_drawer_cash.setStyleSheet(f"background-color: #fafaf9; border: 1px solid #e7e5e4; border-radius: 10px; padding: {drawer_pad}; font-weight: bold; color: #27272a; font-size: {drawer_font};")
        self.lbl_drawer_cash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drawer_row.addWidget(self.lbl_drawer_cash, stretch=4)
        
        self.btn_edit_drawer = QPushButton("✏️", self.categories_sidebar)
        self.btn_edit_drawer.setToolTip("تعديل مبلغ الدرج يدوياً")
        self.btn_edit_drawer.setFixedSize(28 if self.is_small_screen else 32, 28 if self.is_small_screen else 32)
        self.btn_edit_drawer.setObjectName("BtnBlue")
        self.btn_edit_drawer.setStyleSheet(f"font-size: {'11px' if self.is_small_screen else '12px'}; padding: 0;")
        self.btn_edit_drawer.clicked.connect(self.manually_edit_drawer_cash)
        drawer_row.addWidget(self.btn_edit_drawer, stretch=1)
        
        sidebar_main_layout.addLayout(drawer_row)
        
        brand_font = "16px" if self.is_small_screen else "22px"
        brand_title = QLabel("نظام الكاشير", self.categories_sidebar)
        brand_title.setStyleSheet(f"font-size: {brand_font}; font-weight: 900; color: #be123c; border: none; background: transparent;")
        brand_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_main_layout.addWidget(brand_title)
        
        title_hdr_font = "13px" if self.is_small_screen else "16px"
        title_hdr = QLabel("القائمة", self.categories_sidebar)
        title_hdr.setStyleSheet(f"font-size: {title_hdr_font}; font-weight: 900; color: #27272a; border: none; background: transparent;")
        title_hdr.setAlignment(Qt.AlignmentFlag.AlignRight)
        sidebar_main_layout.addWidget(title_hdr)
        
        subtitle_hdr_font = "10px" if self.is_small_screen else "11px"
        subtitle_hdr = QLabel("تصنيفات الطعام", self.categories_sidebar)
        subtitle_hdr.setStyleSheet(f"font-size: {subtitle_hdr_font}; color: #71717a; border: none; background: transparent;")
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
                background-color: transparent; color: #be123c;
                border: 1px dashed #e7a4b5; border-radius: 10px;
                padding: 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #fff1f2; }
        """)
        btn_open_shift_manual.clicked.connect(self.close_shift_and_drawer)
        sidebar_main_layout.addWidget(btn_open_shift_manual)
        
        footer_layout = QHBoxLayout()
        lbl_version = QLabel("V1.0.0 STABLE", self.categories_sidebar)
        lbl_version.setStyleSheet("color: #a0a0a0; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        self.lbl_sidebar_time = QLabel("", self.categories_sidebar)
        self.lbl_sidebar_time.setStyleSheet("color: #616161; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        
        footer_layout.addWidget(lbl_version)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_sidebar_time)
        sidebar_main_layout.addLayout(footer_layout)

        

        
        # Column C: Right checkout cart (410px width)
        self.right_col = QFrame(pos_body)
        self.right_col.setObjectName("PosPanel")
        self.right_col.setMinimumWidth(270 if self.is_small_screen else 300)
        self.right_col.setMaximumWidth(360 if self.is_small_screen else 440)
        self.right_col.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(self.right_col)
        if self.is_small_screen:
            right_layout.setContentsMargins(6, 6, 6, 6)
            right_layout.setSpacing(5)
        else:
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
        self.cust_lookup_box.setObjectName("CustLookupBox")
        self.cust_lookup_box.setStyleSheet("QFrame#CustLookupBox { background: #fafaf9; border: 1px solid #e7e5e4; border-radius: 12px; }")
        
        cust_layout = QVBoxLayout(self.cust_lookup_box)
        if self.is_small_screen:
            cust_layout.setContentsMargins(6, 6, 6, 6)
            cust_layout.setSpacing(4)
        else:
            cust_layout.setContentsMargins(12, 12, 12, 12)
            cust_layout.setSpacing(8)
        
        lookup_row = QHBoxLayout()
        lookup_row.setSpacing(6)
        
        input_h = 28 if self.is_small_screen else 34
        
        self.cust_phone_input = QLineEdit(self.cust_lookup_box)
        self.cust_phone_input.setPlaceholderText("رقم موبايل العميل...")
        self.cust_phone_input.setFixedHeight(input_h)
        self.cust_phone_input.textChanged.connect(self.handle_phone_changed)
        lookup_row.addWidget(self.cust_phone_input)
        
        btn_cust_find = QPushButton("بحث", self.cust_lookup_box)
        btn_cust_find.setFixedHeight(input_h)
        btn_cust_find.setMinimumWidth(60)
        btn_cust_find.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cust_find.clicked.connect(self.trigger_customer_search)
        lookup_row.addWidget(btn_cust_find)
        cust_layout.addLayout(lookup_row)
        
        self.cust_name_input = QLineEdit(self.cust_lookup_box)
        self.cust_name_input.setPlaceholderText("اسم العميل...")
        self.cust_name_input.setFixedHeight(input_h)
        self.cust_name_input.textChanged.connect(self.handle_customer_details_edited)
        cust_layout.addWidget(self.cust_name_input)
        
        self.cust_addr_input = QLineEdit(self.cust_lookup_box)
        self.cust_addr_input.toPlainText = self.cust_addr_input.text
        self.cust_addr_input.setPlaceholderText("عنوان التوصيل بالتفصيل...")
        self.cust_addr_input.setFixedHeight(input_h)
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
        self.scroll_cart.setStyleSheet("background: transparent; border: 1px solid #e7e5e4; border-radius: 12px;")
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
        self.discount_input.setStyleSheet("QLineEdit { background: #ffffff; border: 1px solid #cccccc; border-radius: 6px; color: #1a1a1a; padding: 4px; } QLineEdit:focus { border-color: #0078d4; }")
        self.discount_input.textChanged.connect(self.refresh_cart_display)
        self.discount_input.installEventFilter(self)
        disc_lyt.addWidget(self.discount_input)
        calc_lyt.addWidget(self.discount_charge_row)
        
        # Notes row input
        self.notes_row = QWidget(calc_box)
        notes_lyt = QHBoxLayout(self.notes_row)
        notes_lyt.setContentsMargins(0, 0, 0, 0)
        lbl_notes = QLabel("ملاحظات الطلب:", self.notes_row)
        lbl_notes.setStyleSheet("font-size: 12px; color: #4b5563;")
        notes_lyt.addWidget(lbl_notes)
        self.notes_input = QLineEdit(self.notes_row)
        self.notes_input.setPlaceholderText("زيادة كاتشب، بدون مايونيز...")
        self.notes_input.setStyleSheet("QLineEdit { background: #ffffff; border: 1px solid #cccccc; border-radius: 6px; color: #1a1a1a; padding: 5px; font-size: 12px; } QLineEdit:focus { border-color: #0078d4; }")
        self.notes_input.installEventFilter(self)
        notes_lyt.addWidget(self.notes_input)
        calc_lyt.addWidget(self.notes_row)
        
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
        
        pay_btn_h = 28 if self.is_small_screen else 34
        
        self.btn_pay_cash = QPushButton("كاش / نقدي", self.right_col)
        self.btn_pay_cash.setCheckable(True)
        self.btn_pay_cash.setChecked(True)
        self.btn_pay_cash.setFixedHeight(pay_btn_h)
        self.btn_pay_cash.clicked.connect(lambda: self.switch_payment_method("cash"))
        
        self.btn_pay_visa = QPushButton("فيزا كارت", self.right_col)
        self.btn_pay_visa.setCheckable(True)
        self.btn_pay_visa.setFixedHeight(pay_btn_h)
        self.btn_pay_visa.clicked.connect(lambda: self.switch_payment_method("visa"))
        
        self.btn_pay_wallet = QPushButton("محفظة", self.right_col)
        self.btn_pay_wallet.setCheckable(True)
        self.btn_pay_wallet.setFixedHeight(pay_btn_h)
        self.btn_pay_wallet.clicked.connect(lambda: self.switch_payment_method("wallet"))
        
        pay_row.addWidget(self.btn_pay_cash)
        pay_row.addWidget(self.btn_pay_visa)
        pay_row.addWidget(self.btn_pay_wallet)
        right_layout.addLayout(pay_row)
        
        # Cash drawer presets
        self.cash_calc_widget = QWidget(self.right_col)
        self.cash_calc_lyt = QVBoxLayout(self.cash_calc_widget)
        self.cash_calc_lyt.setContentsMargins(0, 0, 0, 0)
        self.cash_calc_lyt.setSpacing(4)
        
        in_row = QHBoxLayout()
        in_row.addWidget(QLabel("الكاش المدفوع:", self.cash_calc_widget))
        self.paid_input = QLineEdit(self.cash_calc_widget)
        self.paid_input.setText("0")
        self.paid_input.setPlaceholderText("0.0")
        self.paid_input.setFixedHeight(pay_btn_h)
        self.paid_input.textChanged.connect(self.calculate_change_due)
        self.paid_input.installEventFilter(self)
        in_row.addWidget(self.paid_input)
        self.cash_calc_lyt.addLayout(in_row)
        
        # Quick presets row
        self.presets_widget = QWidget(self.cash_calc_widget)
        self.presets_lyt = QHBoxLayout(self.presets_widget)
        self.presets_lyt.setContentsMargins(0, 0, 0, 0)
        self.presets_lyt.setSpacing(4)
        
        presets = [0, 50, 100, 200, 500]
        for val in presets:
            btn_pr = QPushButton(str(val), self.presets_widget)
            btn_pr.setStyleSheet("padding: 4px; font-size: 11px;")
            btn_pr.setMinimumWidth(38)
            btn_pr.setFixedHeight(24 if self.is_small_screen else 30)
            btn_pr.clicked.connect(lambda checked, v=val: self.apply_cash_preset(v))
            self.presets_lyt.addWidget(btn_pr)
        
        self.cash_calc_lyt.addWidget(self.presets_widget)
        
        out_row = QHBoxLayout()
        self.lbl_change_title = QLabel("الباقي للعميل:", self.cash_calc_widget)
        out_row.addWidget(self.lbl_change_title)
        out_row.addStretch()
        self.lbl_change_due = QLabel("0.00 ج.م", self.cash_calc_widget)
        self.lbl_change_due.setStyleSheet(f"font-weight: bold; color: #107c10; font-size: {'13px' if self.is_small_screen else '16px'};")
        out_row.addWidget(self.lbl_change_due)
        self.cash_calc_lyt.addLayout(out_row)
        
        right_layout.addWidget(self.cash_calc_widget)
        
        # Main submit checkout
        self.btn_submit_order = QPushButton("طباعة الفاتورة وتأكيد الدفع", self.right_col)
        self.btn_submit_order.setFixedHeight(36 if self.is_small_screen else 48)
        self.btn_submit_order.clicked.connect(self.checkout_order)
        right_layout.addWidget(self.btn_submit_order)
        
        btn_clear_cart = QPushButton("تفريغ مسح السلة كاملة", self.right_col)
        btn_clear_cart.setObjectName("BtnPink")
        btn_clear_cart.setFixedHeight(26 if self.is_small_screen else 34)
        btn_clear_cart.clicked.connect(self.confirm_clear_cart)
        right_layout.addWidget(btn_clear_cart)
        
        # Add panels to splitter: Categories | Menu Grid | Cart | Active Orders
        self.pos_splitter.addWidget(self.categories_sidebar)
        self.pos_splitter.addWidget(self.center_col)
        self.pos_splitter.addWidget(self.right_col)
        self.pos_splitter.addWidget(self.left_col)
        
        # Set initial proportional sizes (pixels hint)
        if self.is_small_screen:
            self.pos_splitter.setSizes([125, 470, 300, 185])
        else:
            self.pos_splitter.setSizes([170, 620, 360, 240])
        
        # Only the center col (index 1) stretches freely
        self.pos_splitter.setStretchFactor(0, 0)
        self.pos_splitter.setStretchFactor(1, 1)
        self.pos_splitter.setStretchFactor(2, 0)
        self.pos_splitter.setStretchFactor(3, 0)
        
        # Start open; the header button lets the cashier reclaim this space.
        self.pos_splitter.setCollapsible(3, False)
        self._orders_reflow_timer = QTimer(self)
        self._orders_reflow_timer.setSingleShot(True)
        self._orders_reflow_timer.timeout.connect(self.load_pending_delivery_orders)
        self.pos_splitter.splitterMoved.connect(
            lambda *_: self._orders_reflow_timer.start(140)
        )
        self.left_col.setVisible(True)
        self.btn_toggle_orders.setVisible(True)
        
        self.pos_layout.addWidget(self.pos_splitter)

    # ── LOGIN SYSTEM CONTROLS ──
    def setup_login_ui(self):
        layout = QVBoxLayout(self.login_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Outer wrapper
        wrapper = QWidget(self.login_page)
        wrapper.setStyleSheet("background-color: #f5f5f3;")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(20, 20, 20, 20)

        center_container = QFrame(wrapper)
        center_container.setObjectName("LoginCard")
        center_container.setFixedSize(420, 620)
        center_container.setStyleSheet("""
            QFrame#LoginCard {
                background-color: #ffffff;
                border: 1px solid #e7e5e4;
                border-radius: 22px;
            }
        """)

        cc_layout = QVBoxLayout(center_container)
        cc_layout.setSpacing(16)
        cc_layout.setContentsMargins(30, 28, 30, 28)

        # Brand header
        brand_label = QLabel("نظام الكاشير", center_container)
        brand_label.setStyleSheet("font-size: 30px; font-weight: 900; color: #be123c; letter-spacing: 2px; border: none; background: transparent;")
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(brand_label)

        # ── Single shift ──
        lbl_choose = QLabel("وردية واحدة ثابتة باسم DR OMAR", center_container)
        lbl_choose.setStyleSheet("font-size: 13px; font-weight: bold; color: #374151; border: none; background: transparent;")
        lbl_choose.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(lbl_choose)

        cashier_row = QHBoxLayout()
        cashier_row.setSpacing(12)

        self._selected_cashier = None   # will hold (name, pin)

        # Load cashier names from DB
        conn = database.get_connection()
        c = conn.cursor()
        def _get(key): 
            c.execute("SELECT value FROM settings WHERE key=?", (key,))
            r = c.fetchone()
            return r[0] if r else ""
        c1_name = _get("cashier_1_name") or "DR OMAR"
        c1_pin  = _get("cashier_1_pin") or "1111"
        conn.close()

        self._cashiers = [(c1_name, c1_pin)]
        self._selected_cashier = self._cashiers[0]
        self._cashier_btns = []

        for name, pin in self._cashiers:
            btn = QPushButton(f"👤 {name}", center_container)
            btn.setFixedHeight(56)
            btn.setCheckable(True)
            btn.setProperty("cashier_name", name)
            btn.setProperty("cashier_pin", pin)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 15px; font-weight: bold;
                    background-color: #fafaf9; color: #27272a;
                    border: 2px solid #e7e5e4; border-radius: 12px;
                }
                QPushButton:hover { background-color: #fff1f2; border-color: #be123c; color: #9f1239; }
                QPushButton:checked { background-color: #be123c; color: #ffffff; border-color: #be123c; }
            """)
            btn.clicked.connect(lambda checked, b=btn: self._select_cashier_btn(b))
            cashier_row.addWidget(btn)
            self._cashier_btns.append(btn)
            btn.setChecked(True)

        cc_layout.addLayout(cashier_row)

        # PIN Display
        lbl_pin = QLabel("ادخل الرقم السري لبدء الوردية:", center_container)
        lbl_pin.setStyleSheet("font-size: 12px; color: #6b7280; border: none; background: transparent;")
        lbl_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(lbl_pin)

        self.pin_display = QLineEdit(center_container)
        self.pin_display.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setStyleSheet("""
            QLineEdit {
                font-family: 'Courier New', monospace;
                font-size: 28px; letter-spacing: 12px;
                background-color: #fafaf9; border: 2px solid #e7e5e4;
                border-radius: 12px; padding: 10px; color: #18181b;
            }
            QLineEdit:focus { border-color: #be123c; }
        """)
        self.pin_display.setReadOnly(True)
        cc_layout.addWidget(self.pin_display)

        # Touch keypad
        grid_widget = QWidget(center_container)
        grid_widget.setStyleSheet("border: none; background: transparent;")
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح', 3, 0), ('0', 3, 1), ('دخول', 3, 2)
        ]
        for text, row, col in keys:
            btn = QPushButton(text, grid_widget)
            btn.setFixedSize(92, 52)
            if text == 'دخول':
                btn.setStyleSheet("""
                    QPushButton { font-size: 15px; font-weight: bold; background-color: #be123c; color: #ffffff;
                        border: none; border-radius: 10px; }
                    QPushButton:hover { background-color: #9f1239; }
                    QPushButton:pressed { background-color: #881337; }
                """)
                btn.clicked.connect(self.submit_login)
            elif text == 'مسح':
                btn.setStyleSheet("""
                    QPushButton { font-size: 13px; font-weight: bold; background-color: #fff4ce; color: #8a6600;
                        border: 1px solid #fde79a; border-radius: 8px; }
                    QPushButton:hover { background-color: #8a6600; color: #ffffff; }
                """)
                btn.clicked.connect(self.clear_keys)
            else:
                btn.setStyleSheet("""
                    QPushButton { font-size: 18px; font-weight: bold; background-color: #ffffff; color: #1a1a1a;
                        border: 1px solid #dedbd7; border-radius: 10px; }
                    QPushButton:hover { background-color: #fff1f2; border-color: #be123c; color: #9f1239; }
                    QPushButton:pressed { background-color: #ffe4e6; }
                """)
                btn.clicked.connect(lambda checked, t=text: self.press_key(t))
            grid_layout.addWidget(btn, row, col)

        cc_layout.addWidget(grid_widget)

        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(center_container)
        hbox.addStretch()

        wrapper_layout.addStretch()
        wrapper_layout.addLayout(hbox)
        wrapper_layout.addStretch()

        layout.addWidget(wrapper)
        self.password_value = ""

    def _select_cashier_btn(self, clicked_btn):
        """Highlight selected cashier and store selection."""
        for btn in self._cashier_btns:
            btn.setChecked(btn == clicked_btn)
        self._selected_cashier = (
            clicked_btn.property("cashier_name"),
            clicked_btn.property("cashier_pin")
        )
        self.clear_keys()

    def press_key(self, char):
        if len(self.password_value) < 6:
            self.password_value += char
            self.pin_display.setText(self.password_value)

    def clear_keys(self):
        self.password_value = ""
        self.pin_display.setText("")

    def submit_login(self):
        # If no cashier is selected, check if entered PIN matches any cashier's PIN
        if not self._selected_cashier:
            for name, pin in self._cashiers:
                if self.password_value == pin:
                    self._selected_cashier = (name, pin)
                    # Highlight the corresponding button
                    for btn in self._cashier_btns:
                        btn.setChecked(btn.property("cashier_name") == name)
                    break

        if not self._selected_cashier:
            if not self.password_value:
                QMessageBox.warning(self, "بيانات ناقصة", "يرجى كتابة الرقم السري الخاص بك.")
                return
            
            # Let's check if the entered PIN matches any cashier's PIN (in case of wrong selection earlier)
            matched = False
            for name, pin in self._cashiers:
                if self.password_value == pin:
                    self._selected_cashier = (name, pin)
                    # Highlight the button
                    for btn in self._cashier_btns:
                        btn.setChecked(btn.property("cashier_name") == name)
                    matched = True
                    break
            
            if not matched:
                QMessageBox.critical(self, "رقم سري غلط", "الرقم السري الذي أدخلته غير صحيح. أعد المحاولة.")
                self.clear_keys()
                return

        cashier_name, cashier_pin = self._selected_cashier

        # If they selected a cashier but typed a PIN belonging to the other cashier, auto-switch
        if self.password_value != cashier_pin:
            matched = False
            for name, pin in self._cashiers:
                if self.password_value == pin:
                    self._selected_cashier = (name, pin)
                    cashier_name, cashier_pin = name, pin
                    # Highlight the correct button
                    for btn in self._cashier_btns:
                        btn.setChecked(btn.property("cashier_name") == name)
                    matched = True
                    break
            
            if not matched:
                QMessageBox.critical(self, "رقم سري غلط", "الرقم السري اللي كتبته مش صح. حاول تاني.")
                self.clear_keys()
                return

        # Authenticated — store cashier name globally
        config.CURRENT_USER_AUTHENTICATED = True
        config.ACTIVE_CASHIER_NAME = cashier_name

        # Update header label
        if hasattr(self, 'lbl_active_cashier'):
            self.lbl_active_cashier.setText(f"👤 {cashier_name}")

        self.stacked_widget.setCurrentIndex(1)
        self.ensure_active_shift()

    def reload_cashiers_data(self):
        """Reload cashier names and pins dynamically from settings table."""
        conn = database.get_connection()
        c = conn.cursor()
        def _get(key): 
            c.execute("SELECT value FROM settings WHERE key=?", (key,))
            r = c.fetchone()
            return r[0] if r else ""
        c1_name = _get("cashier_1_name") or "DR OMAR"
        c1_pin  = _get("cashier_1_pin") or "1111"
        conn.close()

        self._cashiers = [(c1_name, c1_pin)]
        self._selected_cashier = self._cashiers[0]
        if hasattr(self, '_cashier_btns') and len(self._cashier_btns) == 1:
            self._cashier_btns[0].setText(f"👤 {c1_name}")
            self._cashier_btns[0].setProperty("cashier_name", c1_name)
            self._cashier_btns[0].setProperty("cashier_pin", c1_pin)
            self._cashier_btns[0].setChecked(True)




    def toggle_active_orders_sidebar(self):
        is_visible = self.left_col.isVisible()
        if is_visible:
            # Collapse: save current size then hide
            self._saved_orders_width = self.left_col.width() or 270
            self.left_col.setVisible(False)
            self.btn_toggle_orders.setToolTip("إظهار قسم الطلبات الجارية")
            sizes = self.pos_splitter.sizes()
            sizes[1] += sizes[3] if len(sizes) > 3 else 0
            if len(sizes) > 3:
                sizes[3] = 0
            self.pos_splitter.setSizes(sizes)
        else:
            # Expand: restore or use default width
            target = getattr(self, '_saved_orders_width', 270)
            self.left_col.setVisible(True)
            self.btn_toggle_orders.setToolTip("إخفاء قسم الطلبات الجارية")
            sizes = self.pos_splitter.sizes()
            if len(sizes) > 3:
                # Give space from center col
                sizes[3] = target
                sizes[1] = max(300, sizes[1] - target)
            self.pos_splitter.setSizes(sizes)
        self.load_pending_delivery_orders()


    # ── SHIFT SYSTEM CONTROLS ──
    def ensure_active_shift(self):
        conn = database.get_connection()
        c = conn.cursor()

        # Check if there is an open shift for this cashier
        c.execute("SELECT id, expected_cash, cashier_name FROM shifts WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1")
        open_shift = c.fetchone()

        if open_shift:
            config.ACTIVE_SHIFT_ID = open_shift[0]
            self.lbl_drawer_cash.setText(f"الدرج: {open_shift[1]:,.2f} ج.م")
            # Any open shift belongs to the single active cashier. Historical
            # closed shifts imported from old backups keep their original name.
            if open_shift[2] != config.ACTIVE_CASHIER_NAME and config.ACTIVE_CASHIER_NAME:
                c.execute("UPDATE shifts SET cashier_name=? WHERE id=?", (config.ACTIVE_CASHIER_NAME, open_shift[0]))
                conn.commit()
        else:
            # Create a new shift with the active cashier name
            opened_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute(
                "INSERT INTO shifts (cashier_name, opened_at, expected_cash, actual_cash) VALUES (?, ?, 0.0, 0.0)",
                (config.ACTIVE_CASHIER_NAME, opened_time)
            )
            conn.commit()
            config.ACTIVE_SHIFT_ID = c.lastrowid
            self.lbl_drawer_cash.setText("الدرج: 0.00 ج.م")

        conn.close()
        
    def close_shift_and_drawer(self):
        # Use the custom ExitOptionsDialog to avoid text clipping
        dlg = ExitOptionsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.choice == 'close':
                conn = database.get_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT id
                    FROM orders
                    WHERE shift_id=? AND status IN ('PENDING', 'DISPATCHED')
                    ORDER BY id
                """, (config.ACTIVE_SHIFT_ID,))
                open_order_ids = [row[0] for row in c.fetchall()]
                conn.close()
                if open_order_ids:
                    shown_ids = "، ".join(f"#{order_id}" for order_id in open_order_ids[:12])
                    if len(open_order_ids) > 12:
                        shown_ids += " ..."
                    QMessageBox.warning(
                        self,
                        "لا يمكن إغلاق الوردية",
                        "أنهِ كل الأوردرات المتعلقة بالوردية قبل إغلاقها.\n\n"
                        f"الأوردرات المفتوحة: {shown_ids}",
                    )
                    return
                sdlg = ShiftClosingDialog(self)
                if sdlg.exec() == QDialog.DialogCode.Accepted:
                    closed_shift_id = sdlg.closed_shift_id
                    
                    # Show the beautiful Shift Summary Report Dialog
                    report_dlg = ShiftSummaryReportDialog(closed_shift_id, self)
                    report_dlg.exec()
                    
                    # Logout the user and return to the login screen
                    self.logout()
            elif dlg.choice == 'logout':
                self.logout()

    def logout(self):
        config.CURRENT_USER_AUTHENTICATED = False
        config.ACTIVE_CASHIER_NAME = ""

        # Reload cashier database data dynamically
        self.reload_cashiers_data()

        # Reset cashier selection on login screen
        self._selected_cashier = None
        if hasattr(self, '_cashier_btns'):
            for btn in self._cashier_btns:
                btn.setChecked(False)

        # Reset header cashier label
        if hasattr(self, 'lbl_active_cashier'):
            self.lbl_active_cashier.setText("👤 —")

        # Reset cart and state
        self.cart_items = []
        self.refresh_cart_display()
        self.current_customer_id = None
        self.current_customer_name = ""
        self.current_customer_address = ""

        # Reset customer inputs
        if hasattr(self, 'cust_phone_input'):
            self.cust_phone_input.clear()
        if hasattr(self, 'cust_name_input'):
            self.cust_name_input.clear()
        if hasattr(self, 'cust_addr_input'):
            self.cust_addr_input.clear()

        # Clear discount & notes
        if hasattr(self, 'discount_input'):
            self.discount_input.clear()
        if hasattr(self, 'notes_input'):
            self.notes_input.clear()

        # Reset channel and payment method
        self.switch_channel("cashier")
        self.switch_payment_method("cash")

        # Clear PIN display on login screen
        self.clear_keys()

        # Navigate to login screen
        self.stacked_widget.setCurrentIndex(0)

    def manually_edit_drawer_cash(self):
        """Allow manager to manually set the drawer cash balance."""
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='delete_password'")
        row = c.fetchone()
        manager_pwd = row[0] if row else "456"
        c.execute("SELECT value FROM settings WHERE key='master_password'")
        row2 = c.fetchone()
        master_pwd = row2[0] if row2 else "9999"
        conn.close()

        pdlg = PasswordVerificationDialog(prompt_text="تعديل رصيد الدرج", expected_pwd=[master_pwd, manager_pwd], parent=self)
        if pdlg.exec() != QDialog.DialogCode.Accepted:
            return

        confirm = QMessageBox.question(
            self, "تأكيد تعديل الدرج",
            "هل تود تعديل رصيد الدرج النقدي يدوياً؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Read current balance
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT expected_cash FROM shifts WHERE id=?", (config.ACTIVE_SHIFT_ID,))
        row = c.fetchone()
        conn.close()
        current_val = row[0] if row else 0.0

        # Simple input dialog with touch keypad
        input_dlg = QDialog(self)
        input_dlg.setWindowTitle("تعديل الدرج")
        input_dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        input_dlg.setFixedWidth(540)
        input_dlg.setFixedHeight(290)
        input_dlg.setStyleSheet(STYLE_SHEET)

        main_layout = QHBoxLayout(input_dlg)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Left Column: Inputs & Controls
        left_widget = QWidget(input_dlg)
        left_widget.setStyleSheet("background: transparent; border: none;")
        left_lyt = QVBoxLayout(left_widget)
        left_lyt.setContentsMargins(0, 0, 0, 0)
        left_lyt.setSpacing(12)

        lbl = QLabel(f"أدخل المبلغ الجديد للدرج (الحالي: {current_val:,.2f} ج.م):", left_widget)
        lbl.setWordWrap(True)
        left_lyt.addWidget(lbl)

        amount_input = QLineEdit(left_widget)
        amount_input.setPlaceholderText("0.00")
        amount_input.setText(f"{current_val:.2f}")
        amount_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        amount_input.setStyleSheet("font-size: 20px; font-weight: bold; height: 36px;")
        left_lyt.addWidget(amount_input)

        left_lyt.addStretch()

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("إلغاء", left_widget)
        btn_cancel.setObjectName("BtnDark")
        btn_cancel.setFixedHeight(38)
        btn_cancel.clicked.connect(input_dlg.reject)
        btn_save = QPushButton("💾 حفظ", left_widget)
        btn_save.setFixedHeight(38)
        btn_save.clicked.connect(input_dlg.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        left_lyt.addLayout(btn_row)

        main_layout.addWidget(left_widget, stretch=3)

        # Right Column: Numeric Keypad
        keypad_frame = QWidget(input_dlg)
        keypad_frame.setStyleSheet("background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;")
        keypad_lyt = QVBoxLayout(keypad_frame)
        keypad_lyt.setContentsMargins(8, 8, 8, 8)
        keypad_lyt.setSpacing(4)

        kp_title = QLabel("لوحة أرقام اللمس", keypad_frame)
        kp_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; border: none;")
        kp_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keypad_lyt.addWidget(kp_title)

        grid_widget = QWidget(keypad_frame)
        grid_widget.setStyleSheet("border: none; background: transparent;")
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('←', 3, 0), ('0', 3, 1), ('.', 3, 2)
        ]

        def press_key(char):
            curr = amount_input.text()
            if char == '←':
                amount_input.setText(curr[:-1])
            elif char == '.':
                if '.' not in curr:
                    amount_input.setText(curr + char)
            else:
                if curr == '0':
                    amount_input.setText(char)
                else:
                    amount_input.setText(curr + char)
            amount_input.setFocus()

        for text, row, col in keys:
            btn = QPushButton(text, grid_widget)
            btn.setFixedSize(58, 42)
            if text == '←':
                btn.setStyleSheet("""
                    QPushButton { font-size: 14px; font-weight: bold; background-color: #fef3c7; color: #92400e;
                        border: 1px solid #fde68a; border-radius: 6px; }
                    QPushButton:hover { background-color: #fde68a; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton { font-size: 16px; font-weight: bold; background-color: #ffffff; color: #1f2937;
                        border: 1px solid #e2e8f0; border-radius: 6px; }
                    QPushButton:hover { background-color: #f1f5f9; }
                """)
            btn.clicked.connect(lambda checked, t=text: press_key(t))
            grid_layout.addWidget(btn, row, col)

        keypad_lyt.addWidget(grid_widget)
        main_layout.addWidget(keypad_frame, stretch=2)

        if input_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            new_val = float(amount_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "خطأ", "القيمة المدخلة غير صالحة.")
            return

        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE shifts SET expected_cash = ? WHERE id=?", (new_val, config.ACTIVE_SHIFT_ID))
        conn.commit()
        conn.close()

        self.lbl_drawer_cash.setText(f"الدرج: {new_val:,.2f} ج.م")
        QMessageBox.information(self, "تم التحديث", f"تم تحديث رصيد الدرج إلى {new_val:,.2f} ج.م بنجاح.")

    def delete_order_action(self, order_id):
        """Delete an order after confirmation, deducting cash from drawer if applicable."""
        confirm = QMessageBox.question(
            self, "تأكيد الحذف النهائي",
            f"هل أنت متأكد من حذف الطلب #{order_id} نهائياً من السيستم؟\n"
            "لو كان الطلب تم تحصيله كاش، سيتم خصم قيمته من رصيد الدرج تلقائياً.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        conn = database.get_connection()
        c = conn.cursor()

        # Fetch order payment info to deduct from drawer if cash
        c.execute("SELECT payment_method, total, status, shift_id, driver_id, COALESCE(delivery_fee, 0.0), channel, COALESCE(source, 'POS'), remote_id FROM orders WHERE id=?", (order_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            QMessageBox.warning(self, "خطأ", f"لم يتم العثور على الطلب #{order_id}.")
            return

        pay_method, order_total, status, order_shift_id, driver_id, del_fee, channel, source, remote_id = row
        order_total = order_total or 0.0

        if source == "ONLINE":
            if not remote_id or not hasattr(self, "online_sync"):
                conn.close()
                QMessageBox.critical(
                    self,
                    "تعذر الإلغاء الآمن",
                    "الطلب مرتبط بالموقع لكن رقم المزامنة غير موجود. لم يتم حذفه حتى لا تتأثر نقاط العميل.",
                )
                return
            try:
                self.online_sync.update_remote_order_now(
                    remote_id,
                    status="CANCELLED",
                    cashier_name=config.ACTIVE_CASHIER_NAME,
                )
            except Exception as exc:
                conn.close()
                QMessageBox.critical(
                    self,
                    "تعذر إلغاء الطلب على الموقع",
                    "لم يتم حذف الطلب من السيستم حتى لا تضيع نقاط العميل.\n"
                    f"تأكد أن الموقع شغال ثم حاول مرة ثانية.\n\n{exc}",
                )
                return

        # Revert unsettled cash if it was dispatched
        if driver_id and status == "DISPATCHED":
            driver_owes = (order_total - del_fee) if pay_method == "CASH" else -del_fee
            c.execute("UPDATE drivers SET unsettled_cash = unsettled_cash - ? WHERE id=?", (driver_owes, driver_id))

        # Local cashier cash is added at checkout. Online pickup cash is only
        # added when the order is completed, so deleting it earlier must not
        # change the drawer.
        if pay_method == "CASH" and order_total > 0:
            should_deduct = (status == "COMPLETED") or (channel != "DELIVERY" and source != "ONLINE")
            if should_deduct:
                target_shift = order_shift_id if order_shift_id else config.ACTIVE_SHIFT_ID
                c.execute(
                    "UPDATE shifts SET expected_cash = MAX(0.0, expected_cash - ?) WHERE id=?",
                    (order_total - del_fee, target_shift)
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
                
        cat_font_size = "11px" if self.is_small_screen else "13px"
        cat_height = 36 if self.is_small_screen else 48

        def make_category_button(title, number=""):
            btn = QPushButton(self.categories_container)
            btn.setObjectName("CategoryTab")
            btn.setCheckable(True)
            btn.setFixedHeight(cat_height)
            btn.setStyleSheet(f"""
                QPushButton#CategoryTab {{
                    background-color: transparent; border: none;
                    border-radius: 11px;
                }}
                QPushButton#CategoryTab:hover {{ background-color: #faf0f2; }}
                QPushButton#CategoryTab:checked {{
                    background-color: #fff0f3;
                    border: 1px solid #fbd4dc;
                }}
                QPushButton#CategoryTab QLabel {{
                    background: transparent; border: none; color: #3f3f46;
                    font-weight: 700; font-size: {cat_font_size};
                }}
                QPushButton#CategoryTab:hover QLabel {{ color: #9f1239; }}
                QPushButton#CategoryTab:checked QLabel {{ color: #b51235; font-weight: 900; }}
                QPushButton#CategoryTab QLabel#CategoryNumber {{
                    color: #71717a; background-color: #f4f4f5;
                    border-radius: 8px; padding: 2px 4px;
                    font-size: {"10px" if self.is_small_screen else "11px"};
                    font-weight: 800;
                }}
                QPushButton#CategoryTab:checked QLabel#CategoryNumber {{
                    color: white; background-color: #be123c;
                }}
            """)
            row = QHBoxLayout(btn)
            row.setDirection(QBoxLayout.Direction.LeftToRight)
            row.setContentsMargins(9, 5, 12, 5)
            row.setSpacing(10)

            if number:
                number_label = QLabel(str(number), btn)
                number_label.setObjectName("CategoryNumber")
                number_label.setFixedWidth(25 if self.is_small_screen else 29)
                number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                number_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                row.addWidget(number_label)
            else:
                row.addSpacing(25 if self.is_small_screen else 29)

            title_label = QLabel(title, btn)
            title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(title_label, 1)
            return btn

        # Offers remain first, without an icon or a fake category number.
        btn_offers = make_category_button("العروض")
        btn_offers.setChecked(getattr(self, "_current_cat_id", "offers") == "offers")
        btn_offers.clicked.connect(lambda checked=False: self.filter_category("offers", btn_offers))
        self.cat_sidebar_layout.addWidget(btn_offers)
        self.category_buttons = [btn_offers]

        for display_index, (cat_id, raw_name) in enumerate(cats, start=1):
            display_raw_name = pos_text(raw_name)
            match = re.match(r"^\s*([0-9٠-٩]+)\s*[.\-–—)]*\s*(.+)$", display_raw_name)
            number = match.group(1) if match else str(display_index)
            clean_name = match.group(2).strip() if match else display_raw_name.strip()
            btn = make_category_button(clean_name, number)
            btn.setChecked(getattr(self, "_current_cat_id", "offers") == cat_id)
            btn.clicked.connect(lambda checked, idx=cat_id, b=btn: self.filter_category(idx, b))
            self.cat_sidebar_layout.addWidget(btn)
            self.category_buttons.append(btn)
            
        self.cat_sidebar_layout.addStretch()

    def resizeEvent(self, event):
        """Re-render the menu grid on resize so column count updates dynamically."""
        super().resizeEvent(event)
        if hasattr(self, '_current_cat_id') and hasattr(self, 'menu_grid'):
            # Only re-render if available width changed enough (avoid loop)
            new_w = self.center_col.width() if hasattr(self, 'center_col') else 0
            if new_w > 0:
                new_cols = max(2, min(4, new_w // 175))
                if not hasattr(self, '_last_cols') or self._last_cols != new_cols:
                    self._last_cols = new_cols
                    self.load_menu_items(self._current_cat_id)

    def eventFilter(self, watched, event):
        return super().eventFilter(watched, event)

    def show_keyboard(self, target_input, mode="text"):
        return
            
    def hide_keyboard(self):
        return

    def filter_category(self, cat_id, clicked_btn):
        self.hide_keyboard()
        self._current_cat_id = cat_id
        for btn in self.category_buttons:
            btn.setChecked(btn == clicked_btn)
            
        self.load_menu_items(cat_id)

    def load_menu_items(self, cat_id):
        # Clear grid layout
        for i in reversed(range(self.menu_grid.count())):
            item = self.menu_grid.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        for r in range(self.menu_grid.rowCount()):
            self.menu_grid.setRowStretch(r, 0)

        if cat_id == "offers":
            self.load_offer_cards()
            return
                
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
        # Dynamic column count based on available center col width
        available_w = self.center_col.width() if self.center_col.width() > 0 else 600
        card_min_w = 175  # minimum card width in pixels
        cols_count = max(2, min(4, available_w // card_min_w))

        if not items:
            empty = QLabel(
                "لا توجد أصناف في هذا القسم.",
                self.menu_container,
            )
            empty.setObjectName("MenuEmptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.menu_grid.addWidget(empty, 0, 0, 1, cols_count)
            return
        
        for item_id, name, price, available in items:
            name = pos_text(name) or "صنف"
            card = QFrame(self.menu_container)
            card.setObjectName("MenuItemCard")
            # Compact and uniform size
            card.setMinimumHeight(100)
            card.setMaximumHeight(130 if item_id in item_sizes else 115)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            
            # Card interior layout
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(4)
            
            # Food category emojis
            emoji = "🍗"
            if "سندوتش" in name or "برجر" in name:
                emoji = "🍔" if "برجر" in name else "🌯"
            elif "ريزو" in name:
                emoji = "🍚"
            elif "ستربس" in name or "ستريبس" in name:
                emoji = "🍤"
            elif "بيبسي" in name or "كانز" in name:
                emoji = "🥤"
            elif "بطاطس" in name:
                emoji = "🍟"
            elif "صوص" in name or "تومية" in name or "كولسلو" in name or "مايونيز" in name or "كاتشب" in name:
                emoji = "🍯"
                
            # Header layout to show Name (Right) and Price (Left) inline
            header_layout = QHBoxLayout()
            header_layout.setSpacing(6)
            header_layout.setContentsMargins(0, 0, 0, 0)
            
            lbl_name = QLabel(f"{emoji} {name}", card)
            lbl_name.setWordWrap(True)
            lbl_name.setStyleSheet("font-weight: 800; font-size: 12px; color: #27272a; background: transparent; border: none;")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            lbl_name.setMinimumHeight(35)
            lbl_name.setMaximumHeight(52)
            lbl_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            lbl_price = QLabel(f"{price:.0f} ج.م", card)
            lbl_price.setStyleSheet("font-weight: 900; font-size: 11px; color: #be123c; background: transparent; border: none;")
            lbl_price.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            lbl_price.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            
            # Add widgets to header layout (RTL layout direction will put name on right, price on left)
            header_layout.addWidget(lbl_name)
            header_layout.addWidget(lbl_price)
            card_layout.addLayout(header_layout)
            
            # Add direct adding sizes or single click add
            if item_id in item_sizes:
                sizes_layout = QHBoxLayout()
                sizes_layout.setSpacing(4)
                sizes_layout.setContentsMargins(0, 0, 0, 0)
                for size_name, offset in item_sizes[item_id]:
                    size_name = pos_text(size_name) or "عادي"
                    final_price = price + offset
                    btn_size = QPushButton(f"{size_name}  {final_price:.0f}ج", card)
                    btn_size.setStyleSheet("""
                        QPushButton {
                            background-color: #fafaf9; color: #27272a;
                            border: 1px solid #dedbd7; border-radius: 8px;
                            padding: 3px 4px; font-size: 11px; font-weight: bold;
                        }
                        QPushButton:hover { background-color: #fff1f2; color: #9f1239; border-color: #be123c; }
                        QPushButton:pressed { background-color: #ffe4e6; }
                    """)
                    btn_size.clicked.connect(lambda checked, idx=item_id, n=name, s=size_name, p=final_price: self.add_to_cart_direct(idx, n, s, p))
                    sizes_layout.addWidget(btn_size)
                card_layout.addLayout(sizes_layout)
            else:
                # Make the card itself clickable
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.mousePressEvent = lambda event, idx=item_id, n=name, p=price: self.add_to_cart_direct(idx, n, "عادي", p) if event.button() == Qt.MouseButton.LeftButton else None
                
            # Temporary Disable view if out of stock
            if not available:
                card.setEnabled(False)
                card.setStyleSheet("QFrame#MenuItemCard { background-color: #fde7e9; border: 1px dashed #fbc4c4; }")
                card.mousePressEvent = None
                lbl_price.setText("خلصان ⚠️")
                lbl_price.setStyleSheet("font-weight: bold; font-size: 11px; color: #d13438; background: transparent;")
                for widget in card.findChildren(QWidget):
                    widget.setEnabled(False)
                            
            self.menu_grid.addWidget(card, row, col)
            
            col += 1
            if col >= cols_count:
                col = 0
                row += 1
                
        # Push all card rows to the top by stretching the last empty row
        self.menu_grid.setRowStretch(row + 1, 1)

    def load_offer_cards(self):
        conn = database.get_connection()
        offers = conn.execute(
            "SELECT id, name, offer_price FROM offers WHERE is_active=1 ORDER BY id DESC"
        ).fetchall()
        cards = []
        for offer_id, name, offer_price in offers:
            components = conn.execute(
                """
                SELECT oi.quantity, m.name, m.base_price, m.is_available
                FROM offer_items oi JOIN menu_items m ON m.id=oi.menu_item_id
                WHERE oi.offer_id=? ORDER BY oi.id
                """,
                (offer_id,),
            ).fetchall()
            if not components or any(not row[3] for row in components):
                continue
            regular_price = sum(int(qty) * float(price) for qty, _, price, _ in components)
            component_names = [
                f"{int(qty)}× {pos_text(item_name) or 'صنف'}"
                for qty, item_name, _, _ in components
            ]
            cards.append((
                offer_id, pos_text(name) or "عرض", float(offer_price), regular_price,
                component_names,
            ))
        conn.close()

        available_w = self.center_col.width() if self.center_col.width() > 0 else 600
        cols_count = max(2, min(4, available_w // 175))
        if not cards:
            empty = QLabel(
                "لا توجد عروض متاحة. افتح «إدارة العروض» من أعلى الشاشة.", self.menu_container
            )
            empty.setObjectName("MenuEmptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self.menu_grid.addWidget(empty, 0, 0, 1, cols_count)
            return

        row = col = 0
        for offer_id, name, offer_price, regular_price, components in cards:
            card = QFrame(self.menu_container)
            card.setObjectName("MenuItemCard")
            card.setMinimumHeight(125)
            card.setMaximumHeight(150)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(11, 9, 11, 9)
            layout.setSpacing(5)

            title = QLabel(f"🔥 {name}", card)
            title.setStyleSheet("font-weight: 900; font-size: 13px; color: #27272a; border: none;")
            title.setWordWrap(True)
            layout.addWidget(title)
            component_label = QLabel(" + ".join(components), card)
            component_label.setStyleSheet("font-size: 10px; color: #6b7280; border: none;")
            component_label.setWordWrap(True)
            layout.addWidget(component_label, 1)
            price_label = QLabel(
                f"<span style='color:#9ca3af; text-decoration:line-through;'>{regular_price:.0f} ج.م</span>"
                f" &nbsp; <span style='color:#be123c; font-size:14px; font-weight:900;'>{offer_price:.0f} ج.م</span>",
                card,
            )
            price_label.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(price_label)
            card.mousePressEvent = (
                lambda event, oid=offer_id, n=name, p=offer_price, comps=components:
                self.add_offer_to_cart(oid, n, p, comps)
                if event.button() == Qt.MouseButton.LeftButton else None
            )
            self.menu_grid.addWidget(card, row, col)
            col += 1
            if col >= cols_count:
                col = 0
                row += 1
        self.menu_grid.setRowStretch(row + 1, 1)

    def add_offer_to_cart(self, offer_id, name, price, components):
        self.hide_keyboard()
        for cart_item in self.cart_items:
            if cart_item.get("offer_id") == offer_id:
                cart_item["qty"] += 1
                self.refresh_cart_display()
                return
        self.cart_items.append({
            "id": None,
            "offer_id": offer_id,
            "is_offer": True,
            "name": f"عرض: {name}",
            "size": "باكدج",
            "extras": {component: 0.0 for component in components},
            "base_price": price,
            "price": price,
            "qty": 1,
            "spicy": False,
        })
        self.refresh_cart_display()

    # ── CART MANAGEMENT ──
    def add_to_cart_direct(self, item_id, name, size_name, price):
        self.hide_keyboard()
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
        self.hide_keyboard()
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
            # Premium card design for cart items
            row.setStyleSheet("""
                QFrame#CartItemRow {
                    background-color: #f9fafb;
                    border: 1px solid #e5e7eb;
                    border-radius: 6px;
                }
                QFrame#CartItemRow:hover {
                    background-color: #f3f4f6;
                    border-color: #d1d5db;
                }
            """)
            row.setMinimumHeight(44 if self.is_small_screen else 60)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            
            # Vertical layout to hold the two rows
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(10, 4 if self.is_small_screen else 6, 10, 4 if self.is_small_screen else 6)
            row_layout.setSpacing(2 if self.is_small_screen else 4)
            
            # Row 1: Name (with word wrap) & Delete button
            r1 = QHBoxLayout()
            r1.setSpacing(6)
            
            extras_txt = ", ".join(item["extras"].keys())
            is_offer = item.get("is_offer", False)
            is_spicy = item.get("spicy", False)
            display_txt = f"<b>{item['name']}</b>"
            
            spicy_sz = "11px" if self.is_small_screen else "13px"
            sz_sz = "10px" if self.is_small_screen else "11px"
            ext_sz = "9px" if self.is_small_screen else "10px"
            
            if is_spicy:
                display_txt += f" <span style='color:#ff5050;font-size:{spicy_sz};'>🌶️</span>"
            if item['size'] and item['size'] != 'عادي':
                display_txt += f" <span style='color:#0078d4;font-size:{sz_sz};'>({item['size']})</span>"
            if extras_txt:
                prefix = "المكونات: " if is_offer else "+"
                display_txt += f" <span style='color:#6b7280;font-size:{ext_sz};'>{prefix}{extras_txt}</span>"
            
            info_lbl = QLabel(display_txt, row)
            info_lbl.setWordWrap(True)
            cart_font = "10px" if self.is_small_screen else "12px"
            info_lbl.setStyleSheet(f"border: none; background: transparent; font-size: {cart_font}; color: #1f2937;")
            r1.addWidget(info_lbl, stretch=1)
            
            # Delete button (✕)
            captured_idx = idx
            btn_del = QPushButton("✕", row)
            btn_del.setFixedSize(16 if self.is_small_screen else 20, 16 if self.is_small_screen else 20)
            btn_del_font = "10px" if self.is_small_screen else "12px"
            btn_del.setStyleSheet(f"QPushButton {{ color: #9ca3af; background: transparent; border: none; font-size: {btn_del_font}; padding: 0; }} QPushButton:hover {{ color: #dc2626; }}")
            btn_del.clicked.connect(lambda checked, i=captured_idx: self.remove_cart_item(i))
            r1.addWidget(btn_del)
            
            row_layout.addLayout(r1)
            
            # Row 2: Spicy, QtyControls, Price
            r2 = QHBoxLayout()
            r2.setSpacing(6 if self.is_small_screen else 8)
            
            btn_qty_size = 18 if self.is_small_screen else 22
            btn_spicy_font = "10px" if self.is_small_screen else "12px"
            
            # A bundle has fixed components, so only normal menu items get a spicy toggle.
            if not is_offer:
                btn_spicy = QPushButton("🌶️", row)
                btn_spicy.setFixedSize(btn_qty_size, btn_qty_size)
                btn_spicy.setCheckable(True)
                btn_spicy.setChecked(is_spicy)
                if is_spicy:
                    btn_spicy.setStyleSheet(f"QPushButton {{ background: #fee2e2; border: 1px solid #fca5a5; border-radius: 4px; font-size: {btn_spicy_font}; padding: 0; }}")
                else:
                    btn_spicy.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid #e5e7eb; border-radius: 4px; font-size: {btn_spicy_font}; padding: 0; }} QPushButton:hover {{ border-color: #dc2626; background: #fee2e2; }}")
                btn_spicy.clicked.connect(lambda checked, i=captured_idx: self.toggle_spicy(i))
                r2.addWidget(btn_spicy)
            
            r2.addStretch(1)
            
            # Qty: [−] N [+]
            btn_m = QPushButton("−", row)
            btn_m.setFixedSize(btn_qty_size, btn_qty_size)
            btn_qty_font = "11px" if self.is_small_screen else "13px"
            btn_m.setStyleSheet(f"QPushButton {{ background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; border-radius: 4px; font-weight: bold; font-size: {btn_qty_font}; padding: 0; }} QPushButton:hover {{ background: #b91c1c; color: white; border-color: #b91c1c; }}")
            btn_m.clicked.connect(lambda checked, i=captured_idx: self.adjust_cart_qty(i, -1))
            
            lbl_q = QLabel(str(item["qty"]), row)
            lbl_q.setFixedWidth(20 if self.is_small_screen else 24)
            lbl_q_font = "11px" if self.is_small_screen else "13px"
            lbl_q.setStyleSheet(f"font-weight: 900; font-size: {lbl_q_font}; border: none; background: transparent; color: #374151;")
            lbl_q.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            btn_p = QPushButton("+", row)
            btn_p.setFixedSize(btn_qty_size, btn_qty_size)
            btn_p.setStyleSheet(f"QPushButton {{ background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; border-radius: 4px; font-weight: bold; font-size: {btn_qty_font}; padding: 0; }} QPushButton:hover {{ background: #15803d; color: white; border-color: #15803d; }}")
            btn_p.clicked.connect(lambda checked, i=captured_idx: self.adjust_cart_qty(i, 1))
            
            r2.addWidget(btn_m)
            r2.addWidget(lbl_q)
            r2.addWidget(btn_p)
            
            # Space separator
            r2.addSpacing(6 if self.is_small_screen else 10)
            
            # Line total price
            item_total = item["price"] * item["qty"]
            subtotal += item_total
            lbl_prc = QLabel(f"{item_total:.0f} ج.م", row)
            lbl_prc.setFixedWidth(50 if self.is_small_screen else 60)
            lbl_prc_font = "11px" if self.is_small_screen else "12px"
            lbl_prc.setStyleSheet(f"font-family: monospace; font-weight: 900; font-size: {lbl_prc_font}; color: #107c10; border: none; background: transparent;")
            lbl_prc.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            r2.addWidget(lbl_prc)
            
            row_layout.addLayout(r2)
            
            self.cart_layout.addWidget(row)
            
        self.cart_layout.addStretch()
        
        # Calculate subtotal / grand totals
        self.lbl_subtotal.setText(f"{subtotal:,.2f} ج.م")
        
        delivery_fee = 0.0
        self.delivery_charge_row.setVisible(False)
        
        grand_total = self.get_grand_total()
        self.lbl_grand_total.setText(f"{grand_total:,.2f} ج.م")
        
        self.calculate_change_due()

    def adjust_cart_qty(self, idx, delta):
        self.hide_keyboard()
        new_qty = self.cart_items[idx]["qty"] + delta
        if new_qty >= 1:
            self.cart_items[idx]["qty"] = new_qty
        else:
            self.cart_items.pop(idx)
        self.refresh_cart_display()

    def remove_cart_item(self, idx):
        self.hide_keyboard()
        confirm = QMessageBox.question(
            self, "تأكيد حذف الوجبة",
            "هل تود إزالة هذا الصنف من السلة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.cart_items.pop(idx)
            self.refresh_cart_display()

    def toggle_spicy(self, idx):
        self.hide_keyboard()
        self.cart_items[idx]["spicy"] = not self.cart_items[idx].get("spicy", False)
        self.refresh_cart_display()

    def confirm_clear_cart(self):
        self.hide_keyboard()
        if not self.cart_items:
            return
        confirm = QMessageBox.question(
            self, "تأكيد تفريغ السلة",
            "هل تود مسح وإفراغ السلة بالكامل؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.cart_items = []
            self.refresh_cart_display()

    # ── CUSTOMER AND LOOKUPS ──
    def switch_channel(self, mode):
        self.hide_keyboard()
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
            # If phone already entered, re-run lookup so delivery fields populate
            if self.cust_phone_input.text().strip():
                self.trigger_customer_search()
        
        # Change theme highlighting
        if mode == "cashier":
            self.lbl_grand_total.setStyleSheet("font-size: 24px; font-weight: 800; color: #107c10;")
            self.btn_submit_order.setStyleSheet("QPushButton { background-color: #0078d4; color: #ffffff; } QPushButton:hover { background-color: #106ebe; }")
        else:
            self.lbl_grand_total.setStyleSheet("font-size: 24px; font-weight: 800; color: #0078d4;")
            self.btn_submit_order.setStyleSheet("QPushButton { background-color: #0078d4; color: #ffffff; } QPushButton:hover { background-color: #106ebe; }")

            
        self.refresh_cart_display()

    def handle_phone_changed(self):
        phone = self.cust_phone_input.text().strip()
        # Trigger lookup when phone reaches 11 digits
        if len(phone) >= 11:
            self.trigger_customer_search()
        elif not phone:
            # Clear customer fields when phone is erased
            self.current_customer_id = None
            self.current_customer_name = ""
            self.current_customer_address = ""
            self.cust_name_input.clear()
            self.cust_addr_input.clear()
            self.btn_repeat_order.setVisible(False)

    def trigger_customer_search(self):
        phone = self.cust_phone_input.text().strip()
        if not phone:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        # Search by exact phone or partial match (in case of leading/trailing spaces or country prefix)
        c.execute("SELECT id, name, address FROM customers WHERE phone=? OR phone LIKE ?", (phone, f"%{phone[-9:]}%"))
        cust = c.fetchone()
        conn.close()
        
        if cust:
            self.current_customer_id = cust[0]
            self.current_customer_name = cust[1]
            self.current_customer_address = cust[2] or ""
            
            self.cust_name_input.setText(self.current_customer_name)
            if self.active_channel == "delivery":
                self.cust_addr_input.setText(self.current_customer_address)
            
            # Show repeat previous order button only in delivery
            self.btn_repeat_order.setVisible(self.active_channel == "delivery")
        else:
            # Not found — keep what user typed but clear the id
            self.current_customer_id = None
            self.btn_repeat_order.setVisible(False)

    def update_phone_completer(self):
        """Fetch all stored unique customer phone numbers and attach a search completer to the phone field."""
        try:
            from PyQt6.QtWidgets import QCompleter
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT DISTINCT phone FROM customers WHERE phone IS NOT NULL AND phone != ''")
            phones = [row[0] for row in c.fetchall()]
            conn.close()
            
            if phones:
                completer = QCompleter(phones, self)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                # MatchContains allows matching any part of the phone number (e.g. typing the end of it works)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                
                # Apply a styled drop-down popup
                popup = completer.popup()
                popup.setStyleSheet("""
                    QListView {
                        background-color: #ffffff;
                        color: #1a1a1a;
                        border: 2px solid #cbd5e1;
                        border-radius: 8px;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QListView::item {
                        padding: 8px 12px;
                        border-bottom: 1px solid #f1f5f9;
                    }
                    QListView::item:selected {
                        background-color: #0078d4;
                        color: #ffffff;
                    }
                """)
                completer.activated.connect(self.handle_completer_activated)
                self.cust_phone_input.setCompleter(completer)
        except Exception as e:
            print("Error loading phone completer:", e)

    def handle_completer_activated(self, text):
        """Force database search when a suggested phone number is selected."""
        self.cust_phone_input.setText(text)
        self.trigger_customer_search()

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
            SELECT oi.menu_item_id, COALESCE(oi.item_name, m.name), oi.size_name,
                   oi.quantity, oi.price, oi.extras_json, m.id
            FROM order_items oi
            LEFT JOIN menu_items m ON oi.menu_item_id = m.id
            WHERE oi.order_id=?
        """, (order_id,))
        order_items = c.fetchall()
        
        self.cart_items = []
        unavailable_items = []
        for item_id, name, size_name, qty, price, extras_json, current_item_id in order_items:
            name = pos_text(name) or "صنف"
            size_name = pos_text(size_name) or "عادي"
            if current_item_id is None:
                unavailable_items.append(name or f"#{item_id}")
                continue
            
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
        if unavailable_items:
            QMessageBox.warning(
                self,
                "أصناف غير موجودة",
                "تعذر تكرار الأصناف المحذوفة من المنيو: " + "، ".join(unavailable_items),
            )
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
            self.lbl_change_due.setStyleSheet("font-weight: bold; color: #107c10; font-size: 16px;")
        else:
            remaining = abs(change)
            self.lbl_change_title.setText("⚠️ متبقي على العميل:")
            self.lbl_change_due.setText(f"{remaining:,.2f} ج.م")
            self.lbl_change_due.setStyleSheet("font-weight: bold; color: #b91c1c; font-size: 16px;")

    def get_grand_total(self):
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items)
        delivery_fee = 0.0
        try:
            discount = float(self.discount_input.text()) if hasattr(self, 'discount_input') and self.discount_input.text().strip() else 0.0
        except ValueError:
            discount = 0.0
        return max(0.0, subtotal + delivery_fee - discount)

    def checkout_order(self):
        self.hide_keyboard()
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
            # Cashier/Takeaway: name is optional
            pass
                
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
        delivery_fee = 0.0
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
            # ── لو الحقل فاضي أو صفر أو أقل من الإجمالي ── حط المبلغ الكامل تلقائياً
            if paid <= 0.0:
                paid = grand_total
                self.paid_input.setText(f"{paid:.2f}")
                self.calculate_change_due()
            change = max(0.0, paid - grand_total)
            
        # Cashier orders also start as PENDING until cashier marks done
        status = "PENDING"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        notes = self.notes_input.text().strip() if hasattr(self, 'notes_input') else ""
        c.execute("""
            INSERT INTO orders (customer_id, channel, payment_method, subtotal, delivery_fee, discount, total, cash_paid, change_due, status, shift_id, notes, created_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (customer_id, self.active_channel.upper(), self.payment_method.upper(), subtotal, delivery_fee, discount, grand_total, paid, change, status, config.ACTIVE_SHIFT_ID, notes, now_str, None))
        
        order_id = c.lastrowid
        
        # 3. Insert Items
        for item in self.cart_items:
            item_extras = dict(item["extras"])
            if item.get("spicy", False):
                item_extras["__spicy__"] = True
            c.execute("""
                INSERT INTO order_items (order_id, menu_item_id, item_name, size_name, quantity, price, extras_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_id, item["id"], item["name"], item["size"], item["qty"], item["price"], json.dumps(item_extras)))
            
        # If it's a CASHIER order (Takeaway/Eat In) and payment method is CASH, add to shift expected cash immediately!
        if self.payment_method.upper() == "CASH" and self.active_channel.upper() != "DELIVERY":
            c.execute("UPDATE shifts SET expected_cash = expected_cash + ? WHERE id=?", (grand_total, config.ACTIVE_SHIFT_ID))
            
        conn.commit()
        conn.close()
        
        # 5. Generate Receipt contents
        cashier_receipt = self.generate_receipt_text(order_id, "نسخة الكاشير")
        kitchen_receipt = self.generate_receipt_text(order_id, "نسخة المطبخ")
        
        # Print directly if printer is online, otherwise open preview simulation dialog
        if config.PRINTER_ONLINE:
            from core.printing import print_text_to_printer
            print_text_to_printer(cashier_receipt, self)
            print_text_to_printer(kitchen_receipt, self)
        else:
            psim = ReceiptSimDialog(order_id, cashier_receipt, kitchen_receipt, self)
            psim.exec()
        
        # Clear cart and refresh drawer widgets
        self.cart_items = []
        self.cust_phone_input.clear()
        self.cust_name_input.clear()
        self.cust_addr_input.clear()
        if hasattr(self, 'discount_input'):
            self.discount_input.clear()
        if hasattr(self, 'notes_input'):
            self.notes_input.clear()
        # ── تصفير حقل المبلغ المدفوع بعد كل أوردر ──
        self.paid_input.setText("0")
        self.calculate_change_due()
        self.btn_repeat_order.setVisible(False)
        self.refresh_cart_display()
        self.ensure_active_shift()
        self.load_pending_delivery_orders()
        self.update_phone_completer()

    def generate_receipt_text(self, order_id, copy_title):
        from datetime import datetime
        conn = database.get_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT o.id, o.channel, o.payment_method, o.subtotal, o.delivery_fee, COALESCE(o.discount, 0.0), o.total, o.created_at,
                   cust.name, cust.phone, cust.address, o.cash_paid, o.change_due, o.notes,
                   COALESCE(o.public_number, '')
            FROM orders o
            LEFT JOIN customers cust ON o.customer_id = cust.id
            WHERE o.id=?
        """, (order_id,))
        o_data = c.fetchone()
        
        c.execute("""
            SELECT COALESCE(oi.item_name, m.name), oi.size_name, oi.quantity, oi.price, oi.extras_json
            FROM order_items oi
            LEFT JOIN menu_items m ON oi.menu_item_id = m.id
            WHERE oi.order_id=?
        """, (order_id,))
        o_items = c.fetchall()
        
        if not o_data:
            conn.close()
            return ""

        # Calculate daily order serial number
        order_date_str = o_data[7][:10]  # 'YYYY-MM-DD'
        c.execute("""
            SELECT COUNT(*) FROM orders 
            WHERE substr(created_at, 1, 10) = ? AND id <= ?
        """, (order_date_str, order_id))
        daily_serial = c.fetchone()[0]
        
        conn.close()

        invoice_number = o_data[14] or str(daily_serial)
        is_kitchen = "مطبخ" in copy_title
        
        paper_width = getattr(config, "PAPER_WIDTH", 80)
        
        # Styles optimized depending on paper size (80mm vs 58mm)
        if paper_width == 58:
            body_padding = "2px"
            container_max_width = "100%"
            font_title = "11.5px"
            font_subtitle = "8px"
            font_info = "7.5px"
            font_items = "7.5px"
            font_items_header = "7.5px"
            font_qty = "8.5px"
            font_grand_total = "9.5px"
            font_kitchen_id = "15px"
            font_kitchen_channel = "9px"
            font_notes = "7.5px"
            notes_padding = "4px"
            total_padding = "4px"
            qr_size = "50"
        else:
            body_padding = "8px"
            container_max_width = "400px" # larger and more spaced for 80mm
            font_title = "15px"
            font_subtitle = "9.5px"
            font_info = "8.5px"
            font_items = "9px"
            font_items_header = "9px"
            font_qty = "10px"
            font_grand_total = "13px"
            font_kitchen_id = "20px"
            font_kitchen_channel = "12px"
            font_notes = "9px"
            notes_padding = "8px"
            total_padding = "8px"
            qr_size = "70"

        # Build layout receipt HTML string
        html = []
        html.append("<html dir='rtl'>")
        html.append("<head>")
        html.append("<style>")
        html.append(f"  body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; direction: rtl; text-align: right; margin: 0; padding: {body_padding}; color: #000000; background-color: #ffffff; font-weight: bold; }}")
        html.append(f"  .receipt-container {{ width: 100%; max-width: {container_max_width}; margin: 0 auto; padding: 0; }}")
        html.append("  .center { text-align: center; }")
        html.append("  .bold { font-weight: bold; }")
        html.append("  .divider { border-top: 1px dashed #000000; margin: 8px 0; }")
        html.append("  .solid-divider { border-top: 1px solid #000000; margin: 8px 0; }")
        html.append("  .double-divider { border-top: 3px double #000000; margin: 8px 0; }")
        html.append(f"  .title {{ font-size: {font_title}; font-weight: bold; color: #000000; margin: 4px 0; }}")
        html.append(f"  .subtitle {{ font-size: {font_subtitle}; font-weight: bold; color: #000000; margin-bottom: 4px; }}")
        html.append(f"  .info-table {{ margin: 6px 0; font-size: {font_info}; }}")
        html.append("  .info-table td { padding: 2.5px 0; color: #000000; }")
        html.append(f"  .items-table {{ border-collapse: collapse; margin: 8px 0; font-size: {font_items}; }}")
        html.append(f"  .items-table th {{ border-bottom: 1.5px solid #000000; padding: 4px 0; font-weight: bold; color: #000000; font-size: {font_items_header}; }}")
        html.append("  .items-table td { padding: 5px 0; vertical-align: top; color: #000000; }")
        html.append("  .item-row { border-bottom: 1px dashed #000000; }")
        html.append(f"  .item-qty {{ font-size: {font_qty}; font-weight: bold; color: #000000; }}")
        html.append("  .item-name { font-weight: bold; }")
        html.append("  .item-price { font-weight: bold; }")
        html.append("  .extras { font-size: 9px; color: #000000; padding-right: 8px; margin-top: 1px; }")
        html.append("  .spicy { font-weight: bold; }")
        html.append(f"  .notes-box {{ border: 1.5px solid #000000; padding: {notes_padding}; margin: 8px 0; font-size: {font_notes}; font-weight: bold; color: #000000; background-color: #ffffff; }}")
        html.append(f"  .grand-total {{ font-size: {font_grand_total}; font-weight: bold; color: #000000; border: 2.5px solid #000000; padding: {total_padding}; margin: 10px 0; background-color: #ffffff; text-align: center; }}")
        html.append(f"  .kitchen-id {{ font-size: {font_kitchen_id}; font-weight: bold; background-color: #ffffff; border: 2.5px solid #000000; padding: {total_padding}; margin: 8px 0; text-align: center; }}")
        html.append(f"  .kitchen-channel {{ font-size: {font_kitchen_channel}; font-weight: bold; color: #000000; }}")
        html.append("</style>")
        html.append("</head>")
        html.append("<body dir='rtl'>")
        html.append("<div class='receipt-container'>")
 
        if is_kitchen:
            # ─────────────────────────────────────────────
            # KITCHEN RECEIPT LAYOUT
            # ─────────────────────────────────────────────
            html.append("<div class='center'>")
            html.append(f"<div class='subtitle bold'>{copy_title}</div>")
            html.append(f"<div class='kitchen-id'>طلب رقم {invoice_number}</div>")
            
            channel_text = "دليفري توصيل" if o_data[1] == 'DELIVERY' else "صالة تيك أواي"
            html.append(f"<div class='kitchen-channel'>{channel_text}</div>")
            html.append("</div>")
            
            html.append("<div class='double-divider'></div>")
            html.append("<table class='info-table' width='100%'>")
            html.append(f"<tr><td align='left' width='55%'>{o_data[7]}</td><td class='bold' align='right' width='45%'>تاريخ الطلب:</td></tr>")
            
            if o_data[1] == 'DELIVERY':
                html.append(f"<tr><td align='left' width='55%'>{o_data[8]}</td><td class='bold' align='right' width='45%'>العميل:</td></tr>")
                if o_data[9]:
                    html.append(f"<tr><td align='left' width='55%'>{o_data[9]}</td><td class='bold' align='right' width='45%'>التليفون:</td></tr>")
                if o_data[10]:
                    html.append(f"<tr><td align='left' width='55%'>{o_data[10]}</td><td class='bold' align='right' width='45%'>العنوان:</td></tr>")
            else:
                html.append(f"<tr><td align='left' width='55%'>{o_data[8] or 'صالة / تيك أواي'}</td><td class='bold' align='right' width='45%'>العميل:</td></tr>")
                if o_data[9]:
                    html.append(f"<tr><td align='left' width='55%'>{o_data[9]}</td><td class='bold' align='right' width='45%'>التليفون:</td></tr>")
            html.append("</table>")
            
            html.append("<div class='double-divider'></div>")
            
            # Notes / Special instructions - extremely prominent for kitchen copy
            order_notes = o_data[13] if len(o_data) > 13 and o_data[13] else None
            if order_notes:
                html.append(f"<div class='notes-box'>* تنبيه للمطبخ:<br/>{order_notes}</div>")
            
            # Kitchen items list (larger fonts, no pricing)
            html.append(f"<table class='items-table' width='100%' style='font-size: {'12px' if paper_width == 58 else '15px'};'>")
            html.append("<tr><th align='left' width='25%'>الكمية</th><th align='right' width='75%'>الصنف</th></tr>")
            
            for name, size, qty, price, ext_json in o_items:
                name = pos_text(name) or "صنف"
                size = pos_text(size) or "عادي"
                spicy_flag = False
                ext_dict = {}
                if ext_json:
                    try:
                        parsed = json.loads(ext_json)
                        if isinstance(parsed, dict):
                            spicy_flag = parsed.pop("__spicy__", False)
                            ext_dict = parsed
                    except Exception:
                        pass
                
                spicy_label = " <span class='spicy'>[حار]</span>" if spicy_flag else ""
                
                html.append("<tr class='item-row'>")
                html.append(f"<td align='left' width='25%' class='item-qty'>x{qty}</td>")
                html.append(f"<td align='right' width='75%'><span class='item-name'>{name} ({size})</span>{spicy_label}")
                
                # Extras list under the item
                ext_names = ", ".join(filter(None, (pos_text(key) for key in ext_dict.keys())))
                if ext_names:
                    ext_title = "مكونات العرض" if str(name).startswith("عرض:") else "+ إضافات"
                    html.append(f"<div class='extras'>{ext_title}: {ext_names}</div>")
                html.append("</td>")
                html.append("</tr>")
                
            html.append("</table>")
            html.append("<div class='double-divider'></div>")
            html.append("<div class='center subtitle bold'>يرجى تحضير الطعام بأسرع وقت!</div>")
            
        else:
            # ─────────────────────────────────────────────
            # CASHIER/CUSTOMER RECEIPT LAYOUT
            # ─────────────────────────────────────────────
            html.append("<div class='center'>")
            html.append("<div class='title'>فاتورة الطلب</div>")
            html.append(f"<div class='subtitle'>{copy_title}</div>")
            html.append("</div>")
            
            html.append("<div class='double-divider'></div>")
            html.append("<table class='info-table' width='100%'>")
            html.append(f"<tr><td align='left' width='55%'>{invoice_number}</td><td class='bold' align='right' width='45%'>رقم الفاتورة:</td></tr>")
            html.append(f"<tr><td align='left' width='55%' style='font-size: 13px; font-weight: bold;'>01006593609</td><td class='bold' align='right' width='45%'>تليفون المطعم:</td></tr>")
            html.append(f"<tr><td align='left' width='55%'>{o_data[7]}</td><td class='bold' align='right' width='45%'>التاريخ والوقت:</td></tr>")
            
            if o_data[1] == 'DELIVERY':
                html.append(f"<tr><td align='left' width='55%'>{o_data[8]}</td><td class='bold' align='right' width='45%'>العميل:</td></tr>")
                if o_data[9]:
                    html.append(f"<tr><td align='left' width='55%'>{o_data[9]}</td><td class='bold' align='right' width='45%'>التليفون:</td></tr>")
                if o_data[10]:
                    html.append(f"<tr><td align='left' width='55%'>{o_data[10]}</td><td class='bold' align='right' width='45%'>العنوان:</td></tr>")
            else:
                html.append(f"<tr><td align='left' width='55%'>{o_data[8] or 'صالة / تيك أواي'}</td><td class='bold' align='right' width='45%'>العميل:</td></tr>")
            html.append("</table>")
            
            html.append("<div class='double-divider'></div>")
            
            # Notes for cashier copy - removed as requested
            pass

            # Cashier items list
            html.append("<table class='items-table' width='100%'>")
            html.append("<tr><th align='left' width='25%'>الإجمالي</th><th align='center' width='15%'>العدد</th><th align='right' width='60%'>الوجبة</th></tr>")
            
            for name, size, qty, price, ext_json in o_items:
                name = pos_text(name) or "صنف"
                size = pos_text(size) or "عادي"
                spicy_flag = False
                ext_dict = {}
                if ext_json:
                    try:
                        parsed = json.loads(ext_json)
                        if isinstance(parsed, dict):
                            spicy_flag = parsed.pop("__spicy__", False)
                            ext_dict = parsed
                    except Exception:
                        pass
                
                spicy_label = " <span class='spicy'>[حار]</span>" if spicy_flag else ""
                
                html.append("<tr class='item-row'>")
                html.append(f"<td align='left' width='25%' class='item-price'>{price*qty:.2f} ج.م</td>")
                html.append(f"<td align='center' width='15%'>{qty}</td>")
                html.append(f"<td align='right' width='60%'><span class='item-name'>{name} ({size})</span>{spicy_label}")
                
                ext_names = ", ".join(filter(None, (pos_text(key) for key in ext_dict.keys())))
                if ext_names:
                    ext_title = "مكونات العرض" if str(name).startswith("عرض:") else "+ إضافات"
                    html.append(f"<div class='extras'>{ext_title}: {ext_names}</div>")
                html.append("</td>")
                html.append("</tr>")
                
            html.append("</table>")
            
            html.append("<div class='solid-divider'></div>")
            
            # Grand Total Box ONLY (all other fields removed as requested)
            total = o_data[6]
            html.append("<div class='grand-total'>")
            html.append(f"الإجمالي الكلي: {total:.2f} ج.م")
            html.append("</div>")
            
            # Load QR image and encode to Base64 to prevent broken images
            import base64
            qr_file_path = None
            for path in [
                os.path.join(os.path.dirname(sys.executable), "facebook-qr.jpeg") if getattr(sys, 'frozen', False) else None,
                os.path.join(getattr(sys, '_MEIPASS', ''), "facebook-qr.jpeg") if hasattr(sys, '_MEIPASS') else None,
                os.path.join(database.BASE_DIR, "facebook-qr.jpeg"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "facebook-qr.jpeg")
            ]:
                if path and os.path.exists(path):
                    qr_file_path = path
                    break
            
            qr_img_src = ""
            if qr_file_path:
                try:
                    with open(qr_file_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        qr_img_src = f"data:image/jpeg;base64,{encoded_string}"
                except Exception:
                    pass
            
            if not qr_img_src:
                qr_img_src = f"file:///{os.path.join(database.BASE_DIR, 'facebook-qr.jpeg').replace('\\', '/')}"

            # Facebook QR Code Image at the end
            html.append("<div class='center' style='margin-top: 10px;'>")
            html.append(f"  <img src='{qr_img_src}' width='{qr_size}' height='{qr_size}'/>")
            html.append("  <div style='font-size: 11px; font-weight: bold; margin-top: 6px; color: #000000;'>تابعنا هنا علشان كل جديد</div>")
            html.append("</div>")

        html.append("</div>")
        html.append("</body>")
        html.append("</html>")
        return "".join(html)

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
                   o.cash_paid, o.payment_method, COALESCE(o.source, 'POS'),
                   COALESCE(o.public_number, ''), COALESCE(o.payment_status, ''),
                   COALESCE(o.area_name, ''), o.remote_id,
                   COALESCE(o.customer_trust_status, 'NEW'),
                   COALESCE(o.customer_completed_orders, 0),
                   COALESCE(o.customer_issue_count, 0),
                   COALESCE(o.customer_confirmed_wallets, 0)
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
                    "background: #dff6dd; color: #107c10; "
                    "border: 1px solid #107c10; border-radius: 10px; "
                    "padding: 1px 10px; font-weight: bold; font-size: 12px;"
                )
            else:
                self.orders_count_badge.setStyleSheet(
                    "background: #f3f4f6; color: #6b7280; "
                    "border: 1px solid #d1d5db; border-radius: 10px; "
                    "padding: 1px 10px; font-weight: bold; font-size: 12px;"
                )
        
        # Update header toggle button
        if hasattr(self, 'btn_toggle_orders'):
            toggle_lbl_text = f"الطلبات الجارية ({count})"
            self.btn_toggle_orders.setText(toggle_lbl_text)
            btn_padding = "4px 8px" if self.is_small_screen else "6px 12px"
            btn_font_size = "11px" if self.is_small_screen else "12px"
            if count > 0:
                self.btn_toggle_orders.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #e6f2ff;
                        color: #0078d4;
                        border: 1px solid #b3d7ff;
                        border-radius: 6px;
                        padding: {btn_padding};
                        font-size: {btn_font_size};
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: #d0e7ff;
                    }}
                """)
            else:
                self.btn_toggle_orders.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #ffffff;
                        color: #374151;
                        border: 1px solid #d1d5db;
                        border-radius: 6px;
                        padding: {btn_padding};
                        font-size: {btn_font_size};
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: #f9fafb;
                    }}
                """)
        
        # Empty state
        if not pending:
            empty = QLabel("✓  لا توجد طلبات جارية", self.orders_container)
            empty.setStyleSheet(
                "color: #9ca3af; font-size: 12px; font-weight: bold; "
                "border: 1px dashed #d1d5db; border-radius: 8px; "
                "background: #f9fafb; padding: 18px;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.orders_layout.addWidget(empty)
            return
        
        # Split by channel
        cashier_orders = [o for o in pending if o[7] != 'DELIVERY']
        delivery_orders = [o for o in pending if o[7] == 'DELIVERY']
        
        def make_section_header(text, color, bg):
            lbl = QLabel(text, self.orders_container)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"background: {bg}; color: {color}; border-radius: 6px; "
                f"font-size: 11px; font-weight: bold; padding: 4px 10px; "
                f"border: 1px solid {color};"
            )
            return lbl
        
        def add_order_card(o_id, total, created_at, cust_name, address, status, d_name, channel,
                           cash_paid, pay_method, source, public_number, payment_status,
                           area_name, remote_id, trust_status, completed_orders,
                           issue_count, confirmed_wallets):
            is_delivery = (channel == 'DELIVERY')
            is_online = (source == 'ONLINE')
            content_width = self.scroll_orders.viewport().width()
            is_narrow_card = content_width < 300
            mins_waiting = elapsed_minutes(created_at)
            is_late = mins_waiting >= 15
            is_critical = mins_waiting >= 40

            card = QFrame(self.orders_container)
            card.setObjectName("PendingOrderCard")
            card.setMinimumWidth(0)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.setProperty("delivery", is_delivery)
            card.setProperty("online", is_online)
            if is_critical:
                card.setProperty("critical", True)
            elif is_late:
                card.setProperty("warning", True)
            card.setStyleSheet(STYLE_SHEET)

            c_lyt = QVBoxLayout(card)
            card_margin = 6 if self.is_small_screen or is_narrow_card else 12
            card_padding = 5 if self.is_small_screen else 10
            card_spacing = 4 if self.is_small_screen else 6
            c_lyt.setContentsMargins(card_margin, card_padding, card_margin, card_padding)
            c_lyt.setSpacing(card_spacing)

            r1 = QBoxLayout(
                QBoxLayout.Direction.TopToBottom
                if is_narrow_card else QBoxLayout.Direction.LeftToRight
            )
            icon = "🌐" if is_online else ("🛵" if is_delivery else "🏠")
            display_number = public_number if public_number else f"#{o_id}"
            lbl_id = QLabel(f"{icon}  {display_number}", card)
            lbl_id.setWordWrap(True)
            lbl_id.setMinimumWidth(0)
            lbl_id.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            lbl_id_font = "13px" if self.is_small_screen else "16px"
            lbl_id.setStyleSheet(f"font-weight: 900; font-size: {lbl_id_font}; color: #111827; border: none; background: transparent;")
            r1.addWidget(lbl_id)
            if not is_narrow_card:
                r1.addStretch()
            
            if is_critical:
                timer_color, timer_bg = "#dc2626", "#fee2e2"
            elif is_late:
                timer_color, timer_bg = "#d97706", "#fef3c7"
            else:
                timer_color, timer_bg = "#0078d4", "#e6f2ff"
                
            lbl_time = QLabel(f"⏱ {mins_waiting}د", card)
            lbl_time.setWordWrap(True)
            lbl_time.setMinimumWidth(0)
            lbl_time.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lbl_time_font = "11px" if self.is_small_screen else "13px"
            lbl_time_pad = "2px 4px" if self.is_small_screen else "2px 10px"
            lbl_time.setStyleSheet(
                f"background: {timer_bg}; color: {timer_color}; "
                f"border: 1px solid {timer_color}; border-radius: 4px; "
                f"padding: {lbl_time_pad}; font-size: {lbl_time_font}; font-weight: bold;"
            )
            r1.addWidget(lbl_time)
            c_lyt.addLayout(r1)

            r2 = QBoxLayout(
                QBoxLayout.Direction.TopToBottom
                if is_narrow_card else QBoxLayout.Direction.LeftToRight
            )
            lbl_cust = QLabel(cust_name, card)
            lbl_cust.setWordWrap(True)
            lbl_cust.setMinimumWidth(0)
            lbl_cust.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            lbl_cust_font = "11px" if self.is_small_screen else "13px"
            lbl_cust.setStyleSheet(f"font-size: {lbl_cust_font}; font-weight: bold; color: #374151; border: none; background: transparent;")
            r2.addWidget(lbl_cust)
            if not is_narrow_card:
                r2.addStretch()
            
            cash_val = cash_paid if cash_paid is not None else 0.0
            lbl_price_font = "13px" if self.is_small_screen else "16px"
            if pay_method == 'CASH' and cash_val < total:
                remaining = total - cash_val
                lbl_price = QLabel(f"دفع: {cash_val:.0f} / متبقي: {remaining:.0f} ج", card)
                lbl_price.setStyleSheet(f"font-weight: bold; font-size: 11px; color: #b91c1c; border: none; background: transparent;")
            else:
                lbl_price = QLabel(f"{total:.0f} ج", card)
                lbl_price.setStyleSheet(f"font-weight: 900; font-size: {lbl_price_font}; color: #107c10; border: none; background: transparent;")
            lbl_price.setWordWrap(True)
            lbl_price.setMinimumWidth(0)
            lbl_price.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            r2.addWidget(lbl_price)
            c_lyt.addLayout(r2)

            if is_online:
                payment_labels = {
                    "AWAITING_PAYMENT": "بانتظار التحويل",
                    "PROOF_UPLOADED": "تحويل يحتاج مراجعة",
                    "CONFIRMED": "التحويل مؤكد",
                    "REJECTED": "التحويل مرفوض",
                    "CASH_ON_DELIVERY": "نقدي عند التسليم",
                    "CASH_ON_PICKUP": "نقدي عند الاستلام",
                }
                online_info = payment_labels.get(payment_status, "طلب من الموقع")
                if area_name:
                    online_info = f"{area_name} • {online_info}"
                lbl_online = QLabel(online_info, card)
                lbl_online.setObjectName("OnlineOrderStatus")
                lbl_online.setWordWrap(True)
                lbl_online.setMinimumWidth(0)
                lbl_online.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                c_lyt.addWidget(lbl_online)

                trust_labels = {
                    "RELIABLE": ("موثوق", "#166534", "#dcfce7"),
                    "REGULAR": ("منتظم", "#1d4ed8", "#dbeafe"),
                    "NEEDS_CONFIRMATION": ("يحتاج تأكيد", "#92400e", "#fef3c7"),
                    "UNKNOWN": ("بدون رقم", "#4b5563", "#f3f4f6"),
                    "NEW": ("عميل جديد", "#6b2135", "#fff0f3"),
                }
                trust_label, trust_color, trust_bg = trust_labels.get(
                    trust_status, trust_labels["NEW"]
                )
                trust_text = (
                    f"العميل: {trust_label} • {completed_orders} مكتمل • "
                    f"{issue_count} ملاحظة • {confirmed_wallets} محفظة مؤكدة"
                )
                lbl_trust = QLabel(trust_text, card)
                lbl_trust.setWordWrap(True)
                lbl_trust.setMinimumWidth(0)
                lbl_trust.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                lbl_trust.setStyleSheet(
                    f"background: {trust_bg}; color: {trust_color}; "
                    f"border: 1px solid {trust_color}; border-radius: 5px; "
                    f"padding: 4px 7px; font-size: {'10px' if self.is_small_screen else '11px'}; "
                    "font-weight: bold;"
                )
                c_lyt.addWidget(lbl_trust)

            actions_lyt = QVBoxLayout()
            actions_lyt.setSpacing(3 if self.is_small_screen else 5)

            r3a = QHBoxLayout()
            r3a.setSpacing(0)
            btn_done = QPushButton("✓ خلص", card)
            btn_done.setFixedHeight(28 if self.is_small_screen else 34)
            can_complete = not is_delivery or status == "DISPATCHED"
            btn_done.setEnabled(can_complete)
            if not can_complete:
                btn_done.setToolTip("اختار الطيار أولًا قبل إنهاء طلب الدليفري")
            btn_done_font = "11px" if self.is_small_screen else "13px"
            btn_done.setStyleSheet(
                f"QPushButton {{ background: #dcfce7; color: #15803d; "
                f"border: 1px solid #bbf7d0; border-radius: 6px; "
                f"font-size: {btn_done_font}; font-weight: bold; padding: 0px 6px; }} "
                f"QPushButton:hover {{ background: #15803d; color: white; }} "
                f"QPushButton:disabled {{ background: #f3f4f6; color: #9ca3af; border-color: #d1d5db; }}"
            )
            btn_done.clicked.connect(lambda checked, i=o_id, ch=channel: self.complete_order(i, ch))
            r3a.addWidget(btn_done)
            actions_lyt.addLayout(r3a)

            r3b = QBoxLayout(
                QBoxLayout.Direction.TopToBottom
                if is_narrow_card else QBoxLayout.Direction.LeftToRight
            )
            r3b.setSpacing(3 if self.is_small_screen else 4)

            btn_font = "11px" if self.is_small_screen else "13px"
            btn_h = 26 if self.is_small_screen else 32

            if is_delivery and status == 'PENDING':
                if is_online:
                    dispatch_text = "🛵 جاهز وخرج\nللدليفري" if is_narrow_card else "🛵 جاهز وخرج للدليفري"
                else:
                    dispatch_text = "🛵 تكليف"
                btn_dispatch = QPushButton(dispatch_text, card)
                btn_dispatch.setFixedHeight(40 if is_online and is_narrow_card else btn_h)
                btn_dispatch.setMinimumWidth(0 if is_narrow_card else (55 if self.is_small_screen else 80))
                btn_dispatch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn_dispatch.setStyleSheet(
                    f"QPushButton {{ background: #e6f2ff; color: #0078d4; "
                    f"border: 1px solid #b3d7ff; border-radius: 6px; "
                    f"font-size: {btn_font}; font-weight: bold; padding: 0 5px; }} "
                    f"QPushButton:hover {{ background: #0078d4; color: white; }}"
                )
                btn_dispatch.clicked.connect(lambda checked, idx=o_id: self.dispatch_delivery_order(idx))
                r3b.addWidget(btn_dispatch)
            elif is_delivery and d_name:
                lbl_driver = QLabel(f"🛵 {d_name}", card)
                lbl_driver.setWordWrap(True)
                lbl_driver.setMinimumWidth(0)
                lbl_driver.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                lbl_driver.setStyleSheet(f"font-size: {btn_font}; font-weight: bold; color: #0078d4; border: none; background: transparent;")
                r3b.addWidget(lbl_driver)

            edit_text = "تعديل" if self.is_small_screen else "📝 تعديل"
            btn_edit = QPushButton(edit_text, card)
            btn_edit.setFixedHeight(btn_h)
            btn_edit.setEnabled(not is_online)
            if is_online:
                btn_edit.setToolTip("تفاصيل طلب الموقع ثابتة لحماية الحساب والنقاط")
            btn_edit.setMinimumWidth(0 if is_narrow_card else (55 if self.is_small_screen else 80))
            btn_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn_edit.setStyleSheet(
                f"QPushButton {{ background: #fef3c7; color: #b45309; "
                f"border: 1px solid #fde68a; border-radius: 6px; "
                f"font-size: {btn_font}; font-weight: bold; padding: 0px 4px; }} "
                f"QPushButton:hover {{ background: #fde68a; color: #78350f; }}"
            )
            btn_edit.clicked.connect(lambda checked, idx=o_id: self.open_edit_order_dialog(idx))
            r3b.addWidget(btn_edit)

            btn_delete = QPushButton("🗑 حذف" if is_narrow_card else "🗑", card)
            btn_delete.setFixedHeight(btn_h)
            btn_delete.setMinimumWidth(0 if is_narrow_card else (30 if self.is_small_screen else 40))
            btn_delete.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn_delete.setStyleSheet(
                f"QPushButton {{ background: #fee2e2; color: #b91c1c; "
                f"border: 1px solid #fca5a5; border-radius: 6px; "
                f"font-size: {'12px' if self.is_small_screen else '15px'}; font-weight: bold; padding: 0; }} "
                f"QPushButton:hover {{ background: #dc2626; color: white; }}"
            )
            btn_delete.clicked.connect(lambda checked, idx=o_id: self.delete_order_action(idx))
            r3b.addWidget(btn_delete)
            actions_lyt.addLayout(r3b)

            c_lyt.addLayout(actions_lyt)
            self.orders_layout.addWidget(card)
        
        # ── Section 1: Cashier / Takeaway ──
        if cashier_orders:
            hdr_cashier = make_section_header(f"🏠  تيك أواي وصالة  ({len(cashier_orders)})", "#107c10", "#f0fdf4")
            self.orders_layout.addWidget(hdr_cashier)
            for row in cashier_orders:
                add_order_card(*row)
        
        # ── Separator ──
        if cashier_orders and delivery_orders:
            sep_line = QFrame(self.orders_container)
            sep_line.setFrameShape(QFrame.Shape.HLine)
            sep_line.setStyleSheet("background: #e5e7eb; border: none; max-height: 1px; margin: 4px 0;")
            self.orders_layout.addWidget(sep_line)
        
        # ── Section 2: Delivery ──
        if delivery_orders:
            hdr_delivery = make_section_header(f"🛵  دليفري  ({len(delivery_orders)})", "#0078d4", "#eff6ff")
            self.orders_layout.addWidget(hdr_delivery)
            for row in delivery_orders:
                add_order_card(*row)
        
        count = len(pending)
        
        # Update count badge
        if hasattr(self, 'orders_count_badge'):
            self.orders_count_badge.setText(str(count))
            if count > 0:
                self.orders_count_badge.setStyleSheet(
                    "background: #dff6dd; color: #107c10; "
                    "border: 1px solid #107c10; border-radius: 10px; "
                    "padding: 1px 10px; font-weight: bold; font-size: 12px;"
                )
            else:
                self.orders_count_badge.setStyleSheet(
                    "background: #f3f4f6; color: #6b7280; "
                    "border: 1px solid #d1d5db; border-radius: 10px; "
                    "padding: 1px 10px; font-weight: bold; font-size: 12px;"
                )
        
        # Update header toggle button
        if hasattr(self, 'btn_toggle_orders'):
            self.btn_toggle_orders.setText(f"الطلبات الجارية ({count})")
            if count > 0:
                self.btn_toggle_orders.setStyleSheet("""
                    QPushButton {
                        background-color: #e6f2ff;
                        color: #0078d4;
                        border: 1px solid #b3d7ff;
                        border-radius: 6px;
                        padding: 6px 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #d0e7ff;
                    }
                """)
            else:
                self.btn_toggle_orders.setStyleSheet("""
                    QPushButton {
                        background-color: #ffffff;
                        color: #374151;
                        border: 1px solid #d1d5db;
                        border-radius: 6px;
                        padding: 6px 12px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #f9fafb;
                    }
                """)
        


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
            driver_name = selected_txt.split(" (id:")[0]
            
            conn = database.get_connection()
            c = conn.cursor()
            
            # Revert old driver unsettled cash if order was already dispatched to a driver
            c.execute(
                "SELECT driver_id, total, payment_method, COALESCE(delivery_fee, 0.0), "
                "status, COALESCE(source, 'POS'), remote_id FROM orders WHERE id=?",
                (order_id,),
            )
            old_row = c.fetchone()
            if old_row:
                old_driver_id, tot, pay_method, del_fee, old_status, source, remote_id = old_row
                if source == "ONLINE":
                    if not remote_id or not hasattr(self, "online_sync"):
                        conn.close()
                        QMessageBox.critical(
                            self,
                            "تعذر تحديث حالة الطلب",
                            "الطلب مرتبط بالموقع لكن رقم المزامنة غير موجود. لم يتم تكليف الطيار.",
                        )
                        return
                    try:
                        self.online_sync.update_remote_order_now(
                            remote_id,
                            status="DISPATCHED",
                            driver_name=driver_name,
                            cashier_name=config.ACTIVE_CASHIER_NAME,
                        )
                    except Exception as exc:
                        conn.close()
                        QMessageBox.critical(
                            self,
                            "تعذر تحديث الموقع",
                            "لم يتم تكليف الطيار لأن حالة العميل على الموقع لم تتحدث.\n"
                            f"تأكد أن الموقع شغال ثم حاول مرة ثانية.\n\n{exc}",
                        )
                        return
                if old_driver_id and old_status == 'DISPATCHED':
                    old_owes = (tot - del_fee) if pay_method == "CASH" else -del_fee
                    c.execute("UPDATE drivers SET unsettled_cash = unsettled_cash - ? WHERE id=?", (old_owes, old_driver_id))
            
            # Update new driver unsettled cash
            c.execute("SELECT total, payment_method, COALESCE(delivery_fee, 0.0) FROM orders WHERE id=?", (order_id,))
            tot, pay_method, del_fee = c.fetchone()
            driver_owes = (tot - del_fee) if pay_method == "CASH" else -del_fee
            c.execute("UPDATE drivers SET unsettled_cash = unsettled_cash + ? WHERE id=?", (driver_owes, driver_id))
            
            c.execute(
                "UPDATE orders SET driver_id=?, status='DISPATCHED', "
                "online_status=CASE WHEN source='ONLINE' THEN 'DISPATCHED' ELSE online_status END "
                "WHERE id=?",
                (driver_id, order_id),
            )
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
        c.execute("SELECT total, payment_method, cash_paid, COALESCE(delivery_fee, 0.0), driver_id, status, COALESCE(source, 'POS'), remote_id, shift_id FROM orders WHERE id=?", (order_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        total, method, cash_paid, del_fee, driver_id, old_status, source, remote_id, order_shift_id = row

        if source == "ONLINE":
            if not remote_id or not hasattr(self, "online_sync"):
                conn.close()
                QMessageBox.critical(
                    self,
                    "تعذر إنهاء الطلب",
                    "رقم مزامنة الطلب غير موجود. لم يتم إنهاؤه حتى لا تتأثر حسابات العميل.",
                )
                return
            try:
                self.online_sync.update_remote_order_now(
                    remote_id,
                    status="COMPLETED",
                    cashier_name=config.ACTIVE_CASHIER_NAME,
                )
            except Exception as exc:
                conn.close()
                QMessageBox.critical(
                    self,
                    "تعذر تحديث الموقع",
                    "لم يتم إنهاء الطلب محليًا حتى تظل الحالة والنقاط والحساب متطابقين.\n"
                    f"تأكد أن الموقع شغال ثم حاول مرة ثانية.\n\n{exc}",
                )
                return
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "UPDATE orders SET status='COMPLETED', closed_at=?, "
            "online_status=CASE WHEN source='ONLINE' THEN 'COMPLETED' ELSE online_status END WHERE id=?",
            (now_str, order_id),
        )
        
        # If it was dispatched to a driver, subtract from their unsettled_cash since it's now completed/settled
        if driver_id and old_status == 'DISPATCHED':
            driver_owes = (total - del_fee) if method == "CASH" else -del_fee
            c.execute("UPDATE drivers SET unsettled_cash = unsettled_cash - ? WHERE id=?", (driver_owes, driver_id))
            
        # Local cashier orders are added to the drawer at checkout. Online
        # pickup orders are only paid when handed to the customer, so add them
        # here just like delivery orders.
        if method == "CASH" and (is_delivery or source == "ONLINE"):
            actual_cash = cash_paid if (cash_paid is not None and cash_paid > 0.0) else total
            actual_cash -= del_fee
            target_shift = order_shift_id if order_shift_id else config.ACTIVE_SHIFT_ID
            c.execute("UPDATE shifts SET expected_cash = MAX(0.0, expected_cash + ?) WHERE id=?", (actual_cash, target_shift))
            
        conn.commit()
        conn.close()

        self.load_pending_delivery_orders()
        self.ensure_active_shift()

    def complete_delivery_order(self, order_id):
        """Legacy alias kept for backwards compatibility."""
        self.complete_order(order_id, 'DELIVERY')

    def open_edit_order_dialog(self, order_id):
        conn = database.get_connection()
        row = conn.execute(
            "SELECT COALESCE(source, 'POS') FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        conn.close()
        if row and row[0] == "ONLINE":
            QMessageBox.information(
                self,
                "طلب موقع ثابت",
                "لا يمكن تغيير أصناف أو حساب طلب الموقع بعد إرساله حتى تظل الفاتورة والنقاط متطابقتين. يمكن إلغاؤه ثم إنشاء طلب جديد.",
            )
            return
        dlg = OrderEditDialog(order_id, self)
        dlg.exec()



    # ── MANAGERS / REPORTS OVERLAYS ──
    def open_settings_menu(self):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px 8px 16px;
                font-weight: bold;
                border-radius: 4px;
                background-color: transparent;
                color: #1f2937;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
        """)
        
        action_menu = QAction("📂 إدارة المنيو والتسعير", self)
        action_menu.triggered.connect(self.open_menu_management)
        
        action_printer = QAction("🖨️ إعدادات طابعة الفواتير والورق", self)
        action_printer.triggered.connect(self.open_printer_settings)
        
        action_change_pwd = QAction("🔑 إدارة كلمات المرور (الورديات والنظام)", self)
        action_change_pwd.triggered.connect(self.open_manage_passwords_dialog)

        action_web_sync = QAction("🌐 ربط الموقع والمزامنة", self)
        action_web_sync.triggered.connect(self.open_web_sync_settings)

        action_restore = QAction("📥 استيراد وتحويل Backup قديم", self)
        action_restore.triggered.connect(self.import_backup_from_file)
        
        menu.addAction(action_menu)
        menu.addAction(action_printer)
        menu.addSeparator()
        menu.addAction(action_web_sync)
        menu.addAction(action_change_pwd)
        menu.addSeparator()
        menu.addAction(action_restore)
        
        btn = self.sender()
        if btn:
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def open_web_sync_settings(self):
        from PyQt6.QtWidgets import QCheckBox, QFormLayout

        conn = database.get_connection()
        values = dict(conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('web_sync_enabled', 'web_server_url', 'web_sync_key')"
        ).fetchall())
        conn.close()

        dialog = QDialog(self)
        dialog.setWindowTitle("ربط الموقع والمزامنة")
        dialog.setMinimumWidth(560)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title = QLabel("🌐 ربط برنامج الكاشير بالموقع", dialog)
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        info = QLabel(
            "ضع رابط السيرفر ومفتاح المزامنة. البرنامج يظل يعمل محليًا إذا انقطع الاتصال.",
            dialog,
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        server_input = QLineEdit(dialog)
        server_input.setText(values.get("web_server_url", "http://127.0.0.1:8765"))
        server_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        form.addRow("رابط السيرفر:", server_input)

        key_input = QLineEdit(dialog)
        key_input.setText(values.get("web_sync_key", "broost-local-sync"))
        key_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        form.addRow("مفتاح المزامنة:", key_input)

        enabled_input = QCheckBox("تشغيل مزامنة الموقع", dialog)
        enabled_input.setChecked(values.get("web_sync_enabled", "1") == "1")
        form.addRow("", enabled_input)
        layout.addLayout(form)

        status_card = QFrame(dialog)
        status_card.setObjectName("SyncCheckCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(5)
        status_title = QLabel("حالة الاتصال", status_card)
        status_title.setStyleSheet("font-size: 13px; font-weight: 900; color: #2f2525;")
        status_label = QLabel("اضغط «فحص الاتصال» للتأكد من السيرفر والمفتاح والمزامنة.", status_card)
        status_label.setWordWrap(True)
        status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status_layout.addWidget(status_title)
        status_layout.addWidget(status_label)
        layout.addWidget(status_card)

        def set_check_style(kind, text):
            colors = {
                "idle": ("#f8fafc", "#cbd5e1", "#475569"),
                "loading": ("#eff6ff", "#93c5fd", "#1d4ed8"),
                "success": ("#ecfdf3", "#86efac", "#166534"),
                "warning": ("#fff7ed", "#fdba74", "#9a3412"),
                "error": ("#fff1f2", "#fda4af", "#9f1239"),
            }
            background, border, foreground = colors[kind]
            status_card.setStyleSheet(
                "QFrame#SyncCheckCard {"
                f"background: {background}; border: 1px solid {border}; border-radius: 12px;"
                "}"
                f"QFrame#SyncCheckCard QLabel {{ color: {foreground}; border: none; background: transparent; }}"
            )
            status_label.setText(text)

        buttons = QHBoxLayout()
        cancel = QPushButton("تراجع", dialog)
        cancel.setObjectName("BtnDark")
        cancel.clicked.connect(dialog.reject)
        check = QPushButton("فحص الاتصال", dialog)
        check.setObjectName("BtnDark")
        save = QPushButton("حفظ ومزامنة الآن", dialog)
        buttons.addWidget(cancel)
        buttons.addWidget(check)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        check_state = {"running": False, "result": None, "save_after": False}
        check_timer = QTimer(dialog)
        check_timer.setInterval(100)

        def connection_values():
            return server_input.text().strip().rstrip("/"), key_input.text().strip()

        def save_settings():
            server_url, sync_key = connection_values()
            conn = database.get_connection()
            try:
                conn.executemany(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    [
                        ("web_server_url", server_url),
                        ("web_sync_key", sync_key),
                        ("web_sync_enabled", "1" if enabled_input.isChecked() else "0"),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

        def render_check_result(result):
            server_line = "✅ السيرفر متصل" if result.get("server_ok") else "❌ السيرفر غير متاح"
            if result.get("server_ok"):
                key_line = "✅ مفتاح المزامنة صحيح" if result.get("key_ok") else "❌ مفتاح المزامنة غير صحيح"
            else:
                key_line = "— لم يتم فحص المفتاح"
            sync_line = "✅ مسار المزامنة يعمل" if result.get("sync_ok") else "❌ المزامنة لم تكتمل"
            text = "\n".join((server_line, key_line, sync_line, "", result.get("message", "")))
            if result.get("sync_ok"):
                kind = "success" if result.get("categories") or result.get("items") else "warning"
            elif result.get("server_ok") and result.get("key_ok"):
                kind = "warning"
            else:
                kind = "error"
            set_check_style(kind, text)

        def finish_check():
            result = check_state.get("result")
            if result is None:
                return
            check_timer.stop()
            check_state["running"] = False
            check_state["result"] = None
            check.setEnabled(True)
            save.setEnabled(True)
            server_input.setEnabled(True)
            key_input.setEnabled(True)
            enabled_input.setEnabled(True)
            render_check_result(result)
            if check_state.get("save_after") and result.get("sync_ok"):
                save_settings()
                dialog.accept()
                if hasattr(self, "online_sync"):
                    self.online_sync.poll()
                QMessageBox.information(
                    self,
                    "تم الربط",
                    "تم حفظ الإعدادات وبدأت مزامنة المنيو والطلبات في الخلفية.",
                )

        check_timer.timeout.connect(finish_check)

        def begin_check(save_after=False):
            if check_state["running"]:
                return
            server_url, sync_key = connection_values()
            if not server_url or not sync_key:
                set_check_style("error", "رابط السيرفر ومفتاح المزامنة مطلوبان.")
                return
            if save_after and not enabled_input.isChecked():
                save_settings()
                dialog.accept()
                if hasattr(self, "online_sync"):
                    self.online_sync.poll()
                return
            check_state.update(running=True, result=None, save_after=save_after)
            set_check_style("loading", "⏳ جاري فحص السيرفر والمفتاح ومسار المزامنة...")
            check.setEnabled(False)
            save.setEnabled(False)
            server_input.setEnabled(False)
            key_input.setEnabled(False)
            enabled_input.setEnabled(False)

            def worker():
                try:
                    check_state["result"] = OnlineSyncManager.check_connection(
                        server_url, sync_key
                    )
                except Exception as exc:
                    check_state["result"] = {
                        "server_ok": False,
                        "key_ok": False,
                        "sync_ok": False,
                        "message": f"تعذر إكمال الفحص: {exc}",
                    }

            threading.Thread(target=worker, daemon=True, name="web-sync-check").start()
            check_timer.start()

        check.clicked.connect(lambda: begin_check(False))
        save.clicked.connect(lambda: begin_check(True))
        dialog.exec()

    def open_manage_passwords_dialog(self):
        """Unified Dialog to manage all system and shift passwords/pins with a touch numeric keypad."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QTabWidget, QWidget, QFormLayout, QGridLayout
        from PyQt6.QtCore import Qt
        from dialogs.login import PasswordVerificationDialog

        # Fetch current master password first for access control
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='master_password'")
        row = c.fetchone()
        master_pwd = row[0] if row else "9999"
        conn.close()

        # Ask for manager password to authorize entry
        pdlg = PasswordVerificationDialog(prompt_text="فتح إعدادات كلمات المرور", expected_pwd=master_pwd, parent=self)
        if pdlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Fetch all settings
        conn = database.get_connection()
        c = conn.cursor()
        def _get(key, default):
            c.execute("SELECT value FROM settings WHERE key=?", (key,))
            r = c.fetchone()
            return r[0] if r else default
        
        c1_name = _get("cashier_1_name", "DR OMAR")
        c1_pin  = _get("cashier_1_pin", "1111")
        
        master_pwd = _get("master_password", "9999")
        delete_pwd = _get("delete_password", "9999")
        app_pwd    = _get("app_password", "9999")
        conn.close()

        dlg = QDialog(self)
        dlg.setWindowTitle("🔑 إدارة كلمات المرور")
        dlg.setFixedWidth(660)
        dlg.setFixedHeight(390)
        dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        dlg.setStyleSheet("""
            QDialog {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
            }
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #374151;
                background: transparent;
                border: none;
            }
            QLabel#title_lbl {
                font-size: 16px;
                color: #0078d4;
                font-weight: bold;
            }
            QLineEdit {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
                background: #f9fafb;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
                background: #ffffff;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        title = QLabel("🔑 إدارة كلمات المرور والصلاحيات", dlg)
        title.setObjectName("title_lbl")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Horizontal layout for tabs + keypad
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        tabs = QTabWidget(dlg)
        
        # Tab 1: Single shift
        tab_cashier = QWidget()
        cashier_layout = QFormLayout(tab_cashier)
        cashier_layout.setContentsMargins(10, 15, 10, 15)
        cashier_layout.setSpacing(10)
        
        inp_c1_pin = QLineEdit(tab_cashier)
        inp_c1_pin.setText(c1_pin)
        inp_c1_pin.setPlaceholderText("رقم سري من 4 أرقام")
        inp_c1_pin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        cashier_layout.addRow(QLabel(f"باسورد {c1_name}:"), inp_c1_pin)
        
        tabs.addTab(tab_cashier, "👤 باسورد الوردية")

        # Tab 2: System
        tab_system = QWidget()
        system_layout = QFormLayout(tab_system)
        system_layout.setContentsMargins(10, 15, 10, 15)
        system_layout.setSpacing(10)

        inp_master = QLineEdit(tab_system)
        inp_master.setText(master_pwd)
        inp_master.setPlaceholderText("الباسورد الرئيسي")
        inp_master.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        system_layout.addRow(QLabel("الباسورد الرئيسي (الإعدادات):"), inp_master)

        inp_delete = QLineEdit(tab_system)
        inp_delete.setText(delete_pwd)
        inp_delete.setPlaceholderText("باسورد الحذف والتقارير")
        inp_delete.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        system_layout.addRow(QLabel("باسورد الحذف والتقارير:"), inp_delete)

        inp_app = QLineEdit(tab_system)
        inp_app.setText(app_pwd)
        inp_app.setPlaceholderText("باسورد فتح النظام:")
        inp_app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        system_layout.addRow(QLabel("باسورد شاشة القفل الرئيسية:"), inp_app)

        tabs.addTab(tab_system, "🛡️ صلاحيات النظام")
        content_layout.addWidget(tabs, stretch=3)

        # ── Keypad implementation ──
        dlg.active_input = inp_c1_pin # Default active input
        
        # Setup focus listeners to update active_input reference
        def make_focus_in(widget):
            def focus_in(event):
                QLineEdit.focusInEvent(widget, event)
                dlg.active_input = widget
            return focus_in
            
        inp_c1_pin.focusInEvent = make_focus_in(inp_c1_pin)
        inp_master.focusInEvent = make_focus_in(inp_master)
        inp_delete.focusInEvent = make_focus_in(inp_delete)
        inp_app.focusInEvent    = make_focus_in(inp_app)

        keypad_frame = QWidget(dlg)
        keypad_frame.setStyleSheet("background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;")
        keypad_layout = QVBoxLayout(keypad_frame)
        keypad_layout.setContentsMargins(8, 8, 8, 8)
        keypad_layout.setSpacing(6)

        kp_title = QLabel("لوحة أرقام اللمس", keypad_frame)
        kp_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #64748b; border: none;")
        kp_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keypad_layout.addWidget(kp_title)

        grid_widget = QWidget(keypad_frame)
        grid_widget.setStyleSheet("border: none; background: transparent;")
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(4)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح', 3, 0), ('0', 3, 1), ('←', 3, 2)
        ]

        def press_key(char):
            if hasattr(dlg, 'active_input') and dlg.active_input:
                if char == 'مسح':
                    dlg.active_input.clear()
                elif char == '←':
                    curr = dlg.active_input.text()
                    dlg.active_input.setText(curr[:-1])
                else:
                    curr = dlg.active_input.text()
                    if len(curr) < 8:
                        dlg.active_input.setText(curr + char)
                dlg.active_input.setFocus()

        for text, row, col in keys:
            btn = QPushButton(text, grid_widget)
            btn.setFixedSize(62, 44)
            if text == 'مسح':
                btn.setStyleSheet("""
                    QPushButton { font-size: 12px; font-weight: bold; background-color: #fee2e2; color: #991b1b;
                        border: 1px solid #fca5a5; border-radius: 6px; }
                    QPushButton:hover { background-color: #fca5a5; }
                """)
            elif text == '←':
                btn.setStyleSheet("""
                    QPushButton { font-size: 14px; font-weight: bold; background-color: #fef3c7; color: #92400e;
                        border: 1px solid #fde68a; border-radius: 6px; }
                    QPushButton:hover { background-color: #fde68a; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton { font-size: 16px; font-weight: bold; background-color: #ffffff; color: #1f2937;
                        border: 1px solid #e2e8f0; border-radius: 6px; }
                    QPushButton:hover { background-color: #f1f5f9; }
                """)
            btn.clicked.connect(lambda checked, t=text: press_key(t))
            grid_layout.addWidget(btn, row, col)

        keypad_layout.addWidget(grid_widget)
        content_layout.addWidget(keypad_frame, stretch=2)

        layout.addLayout(content_layout)

        # Buttons
        btn_lyt = QHBoxLayout()
        btn_lyt.setSpacing(10)

        btn_cancel = QPushButton("تراجع", dlg)
        btn_cancel.setFixedHeight(38)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: #f3f4f6; color: #374151;
                border: 1px solid #d1d5db; border-radius: 8px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #e5e7eb; }
        """)
        btn_cancel.clicked.connect(dlg.reject)

        btn_save = QPushButton("حفظ التغييرات ✔", dlg)
        btn_save.setFixedHeight(38)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #0078d4; color: white;
                border: none; border-radius: 8px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #005fa3; }
        """)

        def do_save():
            c1_new = inp_c1_pin.text().strip()
            master_new = inp_master.text().strip()
            delete_new = inp_delete.text().strip()
            app_new = inp_app.text().strip()

            if not c1_new or not master_new or not delete_new or not app_new:
                QMessageBox.warning(dlg, "بيانات ناقصة", "لا يمكن ترك أي كلمة مرور فارغة!")
                return

            # Save all to settings table
            conn2 = database.get_connection()
            c2 = conn2.cursor()
            updates = [
                ("cashier_1_pin", c1_new),
                ("master_password", master_new),
                ("delete_password", delete_new),
                ("app_password", app_new)
            ]
            for k, v in updates:
                c2.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
            conn2.commit()
            conn2.close()

            # Refresh cashier pins in memory so they take effect immediately
            self.reload_cashiers_data()

            dlg.accept()
            QMessageBox.information(self, "تم بنجاح", "✅ تم تحديث جميع كلمات المرور بنجاح.")

        btn_save.clicked.connect(do_save)
        btn_lyt.addWidget(btn_cancel)
        btn_lyt.addWidget(btn_save)
        layout.addLayout(btn_lyt)

        inp_c1_pin.setFocus()
        dlg.exec()

    def open_printer_settings(self):
        from dialogs.printer_settings import PrinterSettingsDialog
        dlg = PrinterSettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.auto_detect_printer_on_startup()

    def open_menu_management(self):
        mdlg = MenuAdminDialog(self)
        if mdlg.exec() == QDialog.DialogCode.Accepted:
            self.load_categories()
            self.load_menu_items(None)

    def open_drivers_management(self):
        dlg = DriversAdminDialog(self)
        dlg.exec()
        self.load_pending_delivery_orders()

    def open_reports_dialog(self):
        # Prompt for verification using the custom password '9999' or manager password
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='delete_password'")
        manager_pwd = c.fetchone()[0]
        c.execute("SELECT value FROM settings WHERE key='master_password'")
        row2 = c.fetchone()
        master_pwd = row2[0] if row2 else "9999"
        conn.close()

        pdlg = PasswordVerificationDialog(prompt_text="فتح لوحة التقارير", expected_pwd=[master_pwd, manager_pwd], parent=self)
        if pdlg.exec() == QDialog.DialogCode.Accepted:
            dlg = ReportsDialog(self)
            dlg.exec()

    def trigger_manual_backup(self):
        success, path = database.run_backup()
        if success:
            QMessageBox.information(self, "نسخة احتياطية ناجحة", f"تم حفظ نسخة احتياطية من قواعد البيانات بنجاح على المسار:\n{path}")
        else:
            QMessageBox.critical(self, "خطأ بالنسخ الاحتياطي", f"حدث خطأ أثناء حفظ النسخة الاحتياطية:\n{path}")

    def import_backup_from_file(self):
        """Validate, migrate, and restore an old Broost POS database backup."""
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='master_password'"
            ).fetchone()
            master_pwd = row[0] if row else "9999"
        finally:
            conn.close()

        password_dialog = PasswordVerificationDialog(
            prompt_text="استيراد وتحويل Backup قديم",
            expected_pwd=master_pwd,
            parent=self,
        )
        if password_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        backup_path, _ = QFileDialog.getOpenFileName(
            self,
            "اختيار Backup برنامج الكاشير القديم",
            database.BACKUP_DIR,
            "POS / SQLite Backup (*.db *.sqlite *.sqlite3 *.backup);;كل الملفات (*.*)",
        )
        if not backup_path:
            return

        answer = QMessageBox.question(
            self,
            "تأكيد استيراد الداتا",
            "سيتم فحص الـBackup وتحويله لإصدار البرنامج الحالي، ثم استبدال "
            "الداتا الموجودة به.\n\n"
            "سيعمل البرنامج نسخة أمان كاملة للداتا الحالية أولًا، ثم يعيد تشغيل نفسه.\n\n"
            "هل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        timer_was_active = (
            hasattr(self, "online_sync_timer") and self.online_sync_timer.isActive()
        )
        if timer_was_active:
            self.online_sync_timer.stop()

        # Do not swap the database while an online-order sync is using it.
        sync_lock = getattr(getattr(self, "online_sync", None), "_busy_lock", None)
        deadline = time.monotonic() + 10
        while sync_lock is not None and sync_lock.locked() and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.05)
        if sync_lock is not None and sync_lock.locked():
            if timer_was_active:
                self.online_sync_timer.start()
            QMessageBox.warning(
                self,
                "المزامنة تعمل الآن",
                "انتظر ثواني حتى تنتهي مزامنة الطلبات، ثم جرّب الاستيراد مرة أخرى.",
            )
            return

        success, result = database.restore_pos_backup(backup_path)
        if not success:
            if timer_was_active:
                self.online_sync_timer.start()
            QMessageBox.critical(self, "لم يتم الاستيراد", str(result))
            return

        QMessageBox.information(
            self,
            "تم استيراد الداتا بنجاح",
            "تم فحص وتحويل الـBackup إلى إصدار البرنامج الحالي.\n\n"
            f"نسخة الرجوع للداتا السابقة محفوظة هنا:\n{result['safety_backup']}\n\n"
            "سيعاد تشغيل البرنامج الآن.",
        )

        app = QApplication.instance()
        shared_memory = getattr(app, "shared_memory", None)
        if shared_memory is not None and shared_memory.isAttached():
            shared_memory.detach()

        if getattr(sys, "frozen", False):
            restart_result = QProcess.startDetached(sys.executable, [], database.BASE_DIR)
        else:
            script_path = os.path.abspath(sys.argv[0])
            restart_result = QProcess.startDetached(
                sys.executable, [script_path], database.BASE_DIR
            )
        restart_started = (
            restart_result[0]
            if isinstance(restart_result, tuple)
            else bool(restart_result)
        )
        if restart_started:
            app.quit()
        else:
            QMessageBox.warning(
                self,
                "أعد فتح البرنامج",
                "تم استيراد الداتا، لكن تعذر تشغيل البرنامج تلقائيًا. "
                "أغلقه وافتحه مرة أخرى لتظهر الداتا الجديدة.",
            )

    def run_automated_daily_backup(self):
        # Check if database has been backed up today
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backup_flag_file = os.path.join(base_dir, ".last_backup_date")
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
                try:
                    with open(backup_flag_file, "w") as f:
                        f.write(today_str)
                except Exception as e:
                    print(f"[Backup Engine] Warning: Could not write last backup date flag: {e}")

    def auto_detect_printer_on_startup(self):
        """Find the default/first physical thermal printer on startup and register it."""
        try:
            btn_padding = "4px 8px" if self.is_small_screen else "6px 12px"
            btn_font_size = "11px" if self.is_small_screen else "12px"

            if not getattr(config, "PRINTER_ONLINE", True):
                self.btn_printer_status.setText("⚠️ طباعة تجريبية")
                self.btn_printer_status.setToolTip("الطباعة الحقيقية متوقفة ويعمل النظام بوضع المحاكاة")
                self.btn_printer_status.setStyleSheet(
                    f"QPushButton {{ background-color: #fff1f2; color: #9f1239; "
                    f"border: 1px solid #fecdd3; border-radius: 10px; "
                    f"padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }}"
                )
                return

            from core.printing import get_physical_printer
            
            # Find the physical printer (it uses cached logic, first call performs search)
            printer = get_physical_printer()
            
            if printer and not printer.isNull():
                config.SELECTED_PRINTER = printer.printerName()
                config.PRINTER_ONLINE = True
                
                display_name = printer.printerName()
                self.btn_printer_status.setText("🖨️ متصلة" if self.is_small_screen else "🖨 الطابعة متصلة")
                self.btn_printer_status.setToolTip(f"الطابعة الحالية: {display_name}")
                self.btn_printer_status.setStyleSheet(
                    f"QPushButton {{ background-color: #eef9f2; color: #157347; "
                    f"border: 1px solid #a7d9bd; border-radius: 10px; "
                    f"padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }}"
                )
            else:
                # No physical printer detected, default to simulation/offline mode
                config.PRINTER_ONLINE = False
                config.SELECTED_PRINTER = ""
                self.btn_printer_status.setText("⚠️ غير موصلة")
                self.btn_printer_status.setToolTip("لا توجد طابعة فعلية موصلة")
                self.btn_printer_status.setStyleSheet(
                    f"QPushButton {{ background-color: #fff1f2; color: #9f1239; "
                    f"border: 1px solid #fecdd3; border-radius: 10px; "
                    f"padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }}"
                )
        except Exception as e:
            print("[Printer Auto-detect] Error finding printer on startup:", e)

    def toggle_printer_connection_sim(self):
        from PyQt6.QtPrintSupport import QPrinterInfo
        from PyQt6.QtWidgets import QInputDialog
        from core.printing import is_virtual_printer
        
        printers = QPrinterInfo.availablePrinters()
        # Only show physical printers (no PDF, XPS, OneNote, Fax, etc.)
        physical_printers = [p for p in printers if not is_virtual_printer(p)]
        printer_names = [p.printerName() for p in physical_printers]
        
        current_printer = getattr(config, "SELECTED_PRINTER", "")
                
        options = ["⚠️ تعطيل الطباعة (وضع المحاكاة)"] + printer_names
        
        if not printer_names:
            options.append("— لا توجد طابعة حقيقية موصلة —")
        
        current_option = "⚠️ تعطيل الطباعة (وضع المحاكاة)" if not config.PRINTER_ONLINE else (current_printer if current_printer in printer_names else options[0])
        
        selected_option, ok = QInputDialog.getItem(
            self, "إعدادات طابعة الفواتير",
            "اختر طابعة الفواتير الحقيقية الموصلة بالجهاز:\n(الطابعات الوهمية مثل PDF و XPS مخفية تلقائياً)",
            options, options.index(current_option) if current_option in options else 0, False
        )
        
        if ok and selected_option:
            btn_padding = "4px 8px" if self.is_small_screen else "6px 12px"
            btn_font_size = "11px" if self.is_small_screen else "12px"
            if selected_option == "⚠️ تعطيل الطباعة (وضع المحاكاة)" or selected_option == "— لا توجد طابعة حقيقية موصلة —":
                config.PRINTER_ONLINE = False
                config.SELECTED_PRINTER = ""
                self.btn_printer_status.setText("⚠️ غير موصلة")
                self.btn_printer_status.setToolTip("لا توجد طابعة فعلية موصلة")
                self.btn_printer_status.setStyleSheet(f"QPushButton {{ background-color: #fff1f2; color: #9f1239; border: 1px solid #fecdd3; border-radius: 10px; padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }}")
            else:
                config.PRINTER_ONLINE = True
                config.SELECTED_PRINTER = selected_option
                self.btn_printer_status.setText("🖨️ متصلة" if self.is_small_screen else "🖨 الطابعة متصلة")
                self.btn_printer_status.setToolTip(f"الطابعة الحالية: {selected_option}")
                self.btn_printer_status.setStyleSheet(f"QPushButton {{ background-color: #eef9f2; color: #157347; border: 1px solid #a7d9bd; border-radius: 10px; padding: {btn_padding}; font-size: {btn_font_size}; font-weight: bold; }}")


    def update_online_sync_status(self, connected, message):
        if not hasattr(self, "lbl_online_sync"):
            return
        if connected:
            self.lbl_online_sync.setText("● متزامن أونلاين")
            self.lbl_online_sync.setProperty("connected", True)
        else:
            normalized = str(message or "")
            if "مزامنة الموقع متوقفة" in normalized:
                status_text = "● المزامنة متوقفة"
            elif "مفتاح المزامنة" in normalized:
                status_text = "● مفتاح المزامنة خطأ"
            elif "خطأ داخلي" in normalized:
                status_text = "● السيرفر متصل - خطأ مزامنة"
            else:
                status_text = "● الموقع غير متصل"
            self.lbl_online_sync.setText(status_text)
            self.lbl_online_sync.setProperty("connected", False)
        self.lbl_online_sync.setToolTip(str(message or ""))
        self.lbl_online_sync.style().unpolish(self.lbl_online_sync)
        self.lbl_online_sync.style().polish(self.lbl_online_sync)

    def open_daily_offers(self):
        dialog = DailyOffersDialog(self)
        dialog.exec()
        if not dialog.saved:
            return
        self._current_cat_id = "offers"
        self.load_categories()
        self.load_menu_items("offers")
        if hasattr(self, "online_sync"):
            self.online_sync.poll()
        QMessageBox.information(
            self,
            "تم نشر العروض",
            "تم حفظ العروض، وسيتم تحديث الموقع تلقائيًا.",
        )

    def reload_menu_after_online_sync(self):
        current_category = getattr(self, "_current_cat_id", None)
        self.load_categories()
        self.load_menu_items(current_category)

    def handle_online_order_received(self, order):
        self.load_pending_delivery_orders()
        self._queue_online_alert(order)

    def handle_online_order_updated(self, order):
        self.load_pending_delivery_orders()
        if order.get("_event_type") in (
            "PAYMENT_PROOF_UPLOADED", "ORDER_CANCELLED_BY_CUSTOMER"
        ):
            self._queue_online_alert(order)

    def _queue_online_alert(self, order):
        alert_key = (order.get("id"), order.get("_event_type"), order.get("payment_status"))
        queued_keys = {
            (item.get("id"), item.get("_event_type"), item.get("payment_status"))
            for item in self._online_alert_queue
        }
        if alert_key not in queued_keys:
            self._online_alert_queue.append(order)
        if not self._online_alert_open:
            QTimer.singleShot(0, self._show_next_online_alert)

    def _show_next_online_alert(self):
        if self._online_alert_open or not self._online_alert_queue:
            return
        self._online_alert_open = True
        order = self._online_alert_queue.pop(0)
        try:
            if order.get("_event_type") == "ORDER_CANCELLED_BY_CUSTOMER":
                CustomerCancelledOrderAlertDialog(order, self).exec()
                return
            dialog = OnlineOrderAlertDialog(order, self)
            dialog.exec()
            if dialog.action == "accept":
                self._accept_online_order(order)
            elif dialog.action == "reject":
                self._reject_online_order(order)
        finally:
            self._online_alert_open = False
            if self._online_alert_queue:
                QTimer.singleShot(150, self._show_next_online_alert)

    def _accept_online_order(self, order):
        local_order_id = order.get("local_order_id")
        remote_id = order.get("id")
        if not local_order_id:
            conn = database.get_connection()
            row = conn.execute("SELECT id FROM orders WHERE remote_id=?", (remote_id,)).fetchone()
            conn.close()
            local_order_id = row[0] if row else None
        if not local_order_id:
            return

        payment_status = order.get("payment_status")
        if order.get("payment_method") == "WALLET" and payment_status == "PROOF_UPLOADED":
            payment_status = "CONFIRMED"

        if not remote_id:
            QMessageBox.critical(self, "تعذر قبول الطلب", "رقم مزامنة الطلب غير موجود.")
            return
        changes = {"status": "PREPARING", "cashier_name": config.ACTIVE_CASHIER_NAME}
        if payment_status:
            changes["payment_status"] = payment_status
        try:
            self.online_sync.update_remote_order_now(remote_id, **changes)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "تعذر قبول الطلب على الموقع",
                "لم يتم قبول الطلب أو طباعته حتى تظل حالته والدفع متطابقين.\n"
                f"تأكد أن الموقع شغال ثم حاول مرة ثانية.\n\n{exc}",
            )
            return

        conn = database.get_connection()
        conn.execute(
            "UPDATE orders SET online_status='PREPARING', payment_status=?, "
            "shift_id=COALESCE(shift_id, ?) WHERE id=?",
            (payment_status, config.ACTIVE_SHIFT_ID, local_order_id),
        )
        conn.commit()
        conn.close()

        cashier_receipt = self.generate_receipt_text(local_order_id, "نسخة الكاشير")
        kitchen_receipt = self.generate_receipt_text(local_order_id, "نسخة المطبخ")
        if config.PRINTER_ONLINE:
            print_text_to_printer(cashier_receipt, self)
            print_text_to_printer(kitchen_receipt, self)
        else:
            ReceiptSimDialog(local_order_id, cashier_receipt, kitchen_receipt, self).exec()

        self.load_pending_delivery_orders()

    def _reject_online_order(self, order):
        local_order_id = order.get("local_order_id")
        remote_id = order.get("id")
        if not local_order_id:
            conn = database.get_connection()
            row = conn.execute("SELECT id FROM orders WHERE remote_id=?", (remote_id,)).fetchone()
            conn.close()
            local_order_id = row[0] if row else None
        if not remote_id:
            QMessageBox.critical(
                self,
                "تعذر رفض الطلب",
                "رقم مزامنة الطلب غير موجود. لم يتم رفضه حتى لا تتأثر نقاط العميل.",
            )
            return
        try:
            self.online_sync.update_remote_order_now(
                remote_id,
                status="CANCELLED",
                cashier_name=config.ACTIVE_CASHIER_NAME,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "تعذر رفض الطلب على الموقع",
                "لم يتم رفض الطلب محليًا حتى لا تضيع نقاط العميل.\n"
                f"تأكد أن الموقع شغال ثم حاول مرة ثانية.\n\n{exc}",
            )
            return
        if local_order_id:
            conn = database.get_connection()
            conn.execute(
                "UPDATE orders SET status='CANCELLED', online_status='CANCELLED', closed_at=? WHERE id=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), local_order_id),
            )
            conn.commit()
            conn.close()
        self.load_pending_delivery_orders()

    def trigger_osk(self):
        import os
        import subprocess
        import ctypes
        
        if os.name == 'nt':
            # Disable WOW64 File System Redirection to access system32/TabTip correctly on 64-bit OS
            class Wow64DisableRedirection:
                def __enter__(self):
                    self.old_value = ctypes.c_void_p()
                    try:
                        ctypes.windll.kernel32.Wow64DisableWow64FsRedirection(ctypes.byref(self.old_value))
                    except:
                        pass
                def __exit__(self, exc_type, exc_val, exc_tb):
                    try:
                        ctypes.windll.kernel32.Wow64RevertWow64FsRedirection(self.old_value)
                    except:
                        pass
            
            try:
                with Wow64DisableRedirection():
                    # Paths to try
                    paths = [
                        r"C:\Program Files\Common Files\microsoft shared\ink\TabTip.exe",
                        r"C:\Program Files (x86)\Common Files\microsoft shared\ink\TabTip.exe",
                        os.environ.get("SystemRoot", "C:\\Windows") + r"\System32\osk.exe"
                    ]
                    
                    launched = False
                    for path in paths:
                        if os.path.exists(path):
                            subprocess.Popen(path)
                            launched = True
                            break
                            
                    if not launched:
                        subprocess.Popen("osk.exe", shell=True)
            except Exception as e:
                try:
                    subprocess.Popen("osk.exe", shell=True)
                except:
                    pass
