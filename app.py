# -*- coding: utf-8 -*-
import sys
import os
from PyQt6.QtWidgets import QApplication, QSplashScreen, QWidget, QVBoxLayout, QLabel, QProgressBar, QFrame
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

import database
from core.runtime_health import install_runtime_protection


install_runtime_protection()

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
    if os.path.exists(logo_ico):
        app.setWindowIcon(QIcon(logo_ico))
        
    # Start and show splash screen
    splash = POSSplashScreen()
    splash.show()
    
    splash.set_message("جاري تجهيز قاعدة البيانات المحلية والتحقق منها...", 15)
    
    database.init_db()
    splash.set_message("جاري إعداد النسخ الاحتياطي وحماية البيانات...", 45)
    
    splash.set_message("جاري فحص الطابعات وتجهيز واجهة المستخدم...", 75)
    
    # Import dashboard inside here to load it after splash is visible
    from views.dashboard import MainPOSDashboard
    dashboard = MainPOSDashboard()
    
    splash.set_message("تم تحميل النظام بنجاح ✔", 100)
    QApplication.processEvents()
    
    splash.close()
    
    dashboard.showMaximized()
    sys.exit(app.exec())
