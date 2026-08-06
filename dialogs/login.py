# -*- coding: utf-8 -*-
"""Broost POS - Login & Password Verification Dialogs"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QMessageBox, QWidget
)
from PyQt6.QtGui import QFont
import database
from styles import STYLE_SHEET
from core import config


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
        
        title_label = QLabel("نظام الكاشير\nالرقم السري لفتح النظام", self)
        title_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #0078d4; background: transparent;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        self.pin_display = QLineEdit(self)
        self.pin_display.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_display.setStyleSheet("font-size: 26px; background: #f9f9f9; border: 1px solid #d9d9d9; padding: 8px; color: #1a1a1a; border-radius: 6px;")
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
                    font-size: 16px; font-weight: bold; background: #ffffff; border: 1px solid #cccccc; color: #1a1a1a; border-radius: 6px;
                }
                QPushButton:hover { background: #f3f3f3; }
            """)
            
            if text == 'دخول':
                btn.setStyleSheet("QPushButton { font-size: 16px; font-weight: bold; background: #0078d4; color: #ffffff; border: 1px solid #0078d4; border-radius: 6px; } QPushButton:hover { background: #106ebe; }")
                btn.clicked.connect(self.submit_login)
            elif text == 'مسح':
                btn.setStyleSheet("QPushButton { font-size: 14px; font-weight: bold; background: #fff4ce; color: #8a6600; border: 1px solid #fde79a; border-radius: 6px; } QPushButton:hover { background: #8a6600; color: white; }")
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
            config.CURRENT_USER_AUTHENTICATED = True
            self.accept()
        else:
            QMessageBox.critical(self, "خطأ بالرقم السري", "الرقم السري الذي أدخلته غير صحيح. أعد المحاولة.")
            self.clear_keys()


class PasswordVerificationDialog(QDialog):
    """Requires the manager password or a custom password to confirm actions."""
    def __init__(self, prompt_text="عملية مسح الطلب", expected_pwd=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تأكيد الصلاحية")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(350, 480)
        self.setStyleSheet(STYLE_SHEET)
        
        self.prompt_text = prompt_text
        self.expected_pwd = expected_pwd
        self.verified = False
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        title = QLabel("تأكيد الصلاحية المطلوبة", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0078d4;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        desc = QLabel(f"إجراء حسّاس: {self.prompt_text}.\nالرجاء إدخال الرقم السري للتأكيد:", self)
        desc.setStyleSheet("color: #616161; font-size: 12px; background: transparent;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        self.pwd_input = QLineEdit(self)
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pwd_input.setStyleSheet("font-size: 20px; background: #f9f9f9; border: 1px solid #d9d9d9; padding: 8px; color: #1a1a1a; border-radius: 6px;")
        layout.addWidget(self.pwd_input)
        
        # Touch Keypad Grid
        grid_widget = QWidget(self)
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(6)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        keys = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('مسح', 3, 0), ('0', 3, 1), ('←', 3, 2)
        ]
        
        for text, row, col in keys:
            btn = QPushButton(text, self)
            btn.setFixedSize(90, 50)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 16px; font-weight: bold; background: #ffffff; border: 1px solid #cccccc; color: #1a1a1a; border-radius: 6px;
                }
                QPushButton:hover { background: #f3f3f3; }
            """)
            
            if text == 'مسح':
                btn.setStyleSheet("QPushButton { font-size: 13px; font-weight: bold; background: #fff4ce; color: #8a6600; border: 1px solid #fde79a; border-radius: 6px; } QPushButton:hover { background: #8a6600; color: white; }")
                btn.clicked.connect(self.clear_keys)
            elif text == '←':
                btn.setStyleSheet("QPushButton { font-size: 16px; font-weight: bold; background: #ffe3e3; color: #c30000; border: 1px solid #fbcaca; border-radius: 6px; } QPushButton:hover { background: #c30000; color: white; }")
                btn.clicked.connect(self.backspace_key)
            else:
                btn.clicked.connect(lambda checked, t=text: self.press_key(t))
                
            grid_layout.addWidget(btn, row, col)
            
        layout.addWidget(grid_widget)
        
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
        
    def press_key(self, char):
        current = self.pwd_input.text()
        if len(current) < 6:
            self.pwd_input.setText(current + char)
            
    def clear_keys(self):
        self.pwd_input.clear()
        
    def backspace_key(self):
        current = self.pwd_input.text()
        if current:
            self.pwd_input.setText(current[:-1])
            
    def verify_password(self):
        entered = self.pwd_input.text().strip()
        
        if self.expected_pwd is not None:
            if isinstance(self.expected_pwd, (list, tuple)):
                is_correct = entered in [str(p) for p in self.expected_pwd]
            else:
                is_correct = (entered == str(self.expected_pwd))
        else:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='delete_password'")
            stored_password = c.fetchone()[0]
            conn.close()
            is_correct = (entered == stored_password)
            
        if is_correct:
            self.verified = True
            self.accept()
        else:
            QMessageBox.critical(self, "خطأ بالرقم السري", "الرقم السري المدخل غير صحيح.")
            self.pwd_input.clear()
