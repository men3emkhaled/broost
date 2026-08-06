# -*- coding: utf-8 -*-
import sys
import os
import time
import socket
import subprocess
from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget, QVBoxLayout, QLabel, QProgressBar, QFrame
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

import database


def ensure_web_server_started():
    """Keep the local ordering site available whenever the POS is running."""
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.4):
            return
    except OSError:
        pass

    if getattr(sys, "frozen", False):
        command = [os.path.join(database.BASE_DIR, "BroostWebServer.exe")]
    else:
        command = [sys.executable, os.path.join(database.BASE_DIR, "run_web.py")]

    if not os.path.exists(command[-1]):
        return

    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        subprocess.Popen(
            command,
            cwd=database.BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except OSError as exc:
        print(f"[Web Server] Could not start: {exc}")

class POSSplashScreen(QSplashScreen):
    def __init__(self):
        super().__init__()
        self.setFixedSize(460, 260)
        
        # Transparent background for the window so card's border radius works perfectly
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        card = QFrame(self)
        card.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(35, 45, 35, 35)
        card_layout.setSpacing(12)
        
        title_label = QLabel("نظام الكاشير", card)
        title_label.setStyleSheet("font-size: 34px; font-weight: 900; color: #38bdf8; border: none;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)
        
        subtitle_label = QLabel("نظام إدارة المبيعات والورديات للمطاعم", card)
        subtitle_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #94a3b8; border: none;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(subtitle_label)
        
        card_layout.addStretch()
        
        self.status_label = QLabel("جاري تشغيل النظام...", card)
        self.status_label.setStyleSheet("font-size: 12px; color: #cbd5e1; font-weight: bold; border: none;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_label)
        
        self.progress = QProgressBar(card)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #334155;
                height: 5px;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 2px;
            }
        """)
        card_layout.addWidget(self.progress)
        
        layout.addWidget(card)
        
    def set_message(self, text, val):
        self.status_label.setText(text)
        self.progress.setValue(val)
        QApplication.processEvents()

if __name__ == "__main__":
    # Fix taskbar icon on Windows
    if os.name == 'nt':
        import ctypes
        try:
            myappid = 'broost.pos.system.v1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    # Single instance lock using QSharedMemory
    from PyQt6.QtCore import QSharedMemory
    from PyQt6.QtWidgets import QMessageBox
    
    shared_memory = QSharedMemory("BroostPOS_Single_Instance_Mutex")
    if not shared_memory.create(1):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("تنبيه")
        msg.setText("البرنامج قيد التشغيل بالفعل!")
        msg.setInformativeText("لا يمكن تشغيل أكثر من نسخة من البرنامج في نفس الوقت لتجنب تلف قاعدة البيانات.")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        # Fix RTL layout for Arabic message box
        msg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        msg.exec()
        sys.exit(0)
        
    # Keep the shared memory reference alive
    app.shared_memory = shared_memory
    
    # Set custom window icon (prefer .ico on Windows for crisp taskbar/title bar)
    logo_ico = os.path.join(database.BASE_DIR, "logo.ico")
    logo_png = os.path.join(database.BASE_DIR, "logo.png")
    if os.path.exists(logo_ico):
        app.setWindowIcon(QIcon(logo_ico))
    elif os.path.exists(logo_png):
        app.setWindowIcon(QIcon(logo_png))
        
    # Start and show splash screen
    splash = POSSplashScreen()
    splash.show()
    
    splash.set_message("جاري الاتصال بقاعدة البيانات والتحقق منها...", 15)
    time.sleep(0.6)
    
    database.init_db()
    ensure_web_server_started()
    splash.set_message("جاري إعداد النسخ الاحتياطي وحماية البيانات...", 45)
    time.sleep(0.6)
    
    splash.set_message("جاري فحص الطابعات وتجهيز واجهة المستخدم...", 75)
    time.sleep(0.6)
    
    # Import dashboard inside here to load it after splash is visible
    from views.dashboard import MainPOSDashboard
    dashboard = MainPOSDashboard()
    
    splash.set_message("تم تحميل النظام بنجاح ✔", 100)
    time.sleep(0.5)
    
    splash.close()
    
    dashboard.showMaximized()
    sys.exit(app.exec())
