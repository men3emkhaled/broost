# -*- coding: utf-8 -*-
"""Broost POS - Printer & Print Settings Dialog"""
import sqlite3
import os
from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QRadioButton, QButtonGroup, QFrame, QMessageBox,
    QGroupBox, QWidget
)
import database
from styles import STYLE_SHEET
from core import config
from core.printing import print_text_to_printer, is_virtual_printer


class PrinterSettingsDialog(QDialog):
    """Dialog to configure printing options (Printer selection, Paper size, and test printing)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إعدادات طابعة الفواتير")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(520, 390)
        self.setStyleSheet(STYLE_SHEET)
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # ── Header ──
        header = QHBoxLayout()
        title = QLabel("🖨️ إعدادات طابعة الفواتير والورق", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet(
            "QPushButton { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-weight: bold; font-size: 13px; padding: 0; }"
            "QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }"
        )
        btn_close.clicked.connect(self.reject)
        header.addWidget(btn_close)
        main_layout.addLayout(header)

        # ── Divider ──
        div = QFrame(self)
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #e5e7eb; max-height: 1px; border: none;")
        main_layout.addWidget(div)

        # ── 1. Printer Selector Group ──
        group_printer = QGroupBox("طابعة الفواتير المحددة", self)
        group_printer.setStyleSheet("QGroupBox { font-size: 12px; }")
        layout_printer = QVBoxLayout(group_printer)
        layout_printer.setContentsMargins(12, 16, 12, 12)
        layout_printer.setSpacing(8)

        self.printer_dropdown = QComboBox(group_printer)
        self.printer_dropdown.setFixedHeight(34)
        
        # Populate printers list
        printers = QPrinterInfo.availablePrinters()
        physical_printers = [p for p in printers if not is_virtual_printer(p)]
        printer_names = [p.printerName() for p in physical_printers]
        
        self.printer_dropdown.addItem("⚠️ وضع المحاكاة (تعطيل الطباعة الورقية)")
        for name in printer_names:
            self.printer_dropdown.addItem(name)
            
        layout_printer.addWidget(self.printer_dropdown)
        main_layout.addWidget(group_printer)

        # ── 2. Paper Size Group ──
        group_paper = QGroupBox("حجم وعرض ورق الطباعة", self)
        group_paper.setStyleSheet("QGroupBox { font-size: 12px; }")
        layout_paper = QVBoxLayout(group_paper)
        layout_paper.setContentsMargins(12, 16, 12, 12)
        layout_paper.setSpacing(8)

        self.radio_80 = QRadioButton("ورق كبير (80mm - طابعة الكاشير العادية)", group_paper)
        self.radio_80.setStyleSheet("QRadioButton { font-weight: bold; font-size: 13px; }")
        layout_paper.addWidget(self.radio_80)

        self.radio_58 = QRadioButton("ورق صغير (58mm - مكن فوري / الطابعات المحمولة)", group_paper)
        self.radio_58.setStyleSheet("QRadioButton { font-weight: bold; font-size: 13px; }")
        layout_paper.addWidget(self.radio_58)

        # Group radio buttons together
        self.paper_group = QButtonGroup(self)
        self.paper_group.addButton(self.radio_80)
        self.paper_group.addButton(self.radio_58)

        main_layout.addWidget(group_paper)

        # ── Divider ──
        div2 = QFrame(self)
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("background: #e5e7eb; max-height: 1px; border: none;")
        main_layout.addWidget(div2)

        # ── Actions Row ──
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        # Test Print Button
        self.btn_test = QPushButton("🖨️ تجربة الطباعة (Test)", self)
        self.btn_test.setFixedHeight(36)
        self.btn_test.setStyleSheet(
            "QPushButton { background-color: #fef3c7; color: #b45309; border: 1px solid #fde68a; border-radius: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #fde68a; }"
        )
        self.btn_test.clicked.connect(self.trigger_test_print)
        actions_layout.addWidget(self.btn_test, stretch=2)

        # Save Button
        self.btn_save = QPushButton("💾 حفظ الإعدادات", self)
        self.btn_save.setFixedHeight(36)
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #106ebe; }"
        )
        self.btn_save.clicked.connect(self.save_settings)
        actions_layout.addWidget(self.btn_save, stretch=3)

        # Cancel Button
        self.btn_cancel = QPushButton("إلغاء", self)
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #f3f4f6; color: #374151; border: 1px solid #d1d5db; border-radius: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #e5e7eb; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        actions_layout.addWidget(self.btn_cancel, stretch=1)

        main_layout.addLayout(actions_layout)

    def load_settings(self):
        # Load from database
        try:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT key, value FROM settings WHERE key IN ('printer_paper_width', 'selected_printer', 'printer_online')")
            db_settings = dict(c.fetchall())
            conn.close()

            # Set values
            saved_printer = db_settings.get("selected_printer", "")
            saved_width = int(db_settings.get("printer_paper_width", "80"))
            saved_online = db_settings.get("printer_online", "1") == "1"

            # Set dropdown
            if not saved_online or not saved_printer:
                self.printer_dropdown.setCurrentIndex(0)
            else:
                index = self.printer_dropdown.findText(saved_printer)
                if index >= 0:
                    self.printer_dropdown.setCurrentIndex(index)
                else:
                    self.printer_dropdown.setCurrentIndex(0)

            # Set radio buttons
            if saved_width == 58:
                self.radio_58.setChecked(True)
            else:
                self.radio_80.setChecked(True)
        except Exception as e:
            print("Error loading dialog settings:", e)
            self.radio_80.setChecked(True)

    def trigger_test_print(self):
        selected_option = self.printer_dropdown.currentText()
        if selected_option == "⚠️ وضع المحاكاة (تعطيل الطباعة الورقية)":
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار طابعة فواتير حقيقية لتتمكن من إجراء اختبار الطباعة.")
            return

        # Temporarily apply selections to config to test
        old_online = config.PRINTER_ONLINE
        old_printer = config.SELECTED_PRINTER
        old_width = config.PAPER_WIDTH

        config.PRINTER_ONLINE = True
        config.SELECTED_PRINTER = selected_option
        config.PAPER_WIDTH = 58 if self.radio_58.isChecked() else 80

        # Build test receipt HTML
        paper_w = config.PAPER_WIDTH
        body_padding = "2px" if paper_w == 58 else "8px"
        container_max_w = "100%" if paper_w == 58 else "450px"
        font_title = "15px" if paper_w == 58 else "22px"
        font_sub = "10px" if paper_w == 58 else "13px"
        font_info = "9px" if paper_w == 58 else "11px"

        test_html = f"""
        <html dir='rtl'>
        <head>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; direction: rtl; text-align: right; margin: 0; padding: {body_padding}; color: #000000; background-color: #ffffff; }}
            .receipt-container {{ width: 100%; max-width: {container_max_w}; margin: 0 auto; padding: 0; }}
            .center {{ text-align: center; }}
            .divider {{ border-top: 1px dashed #000000; margin: 8px 0; }}
            .title {{ font-size: {font_title}; font-weight: bold; color: #000000; margin: 4px 0; }}
            .subtitle {{ font-size: {font_sub}; font-weight: bold; color: #000000; margin-bottom: 4px; }}
            .info-table {{ margin: 6px 0; font-size: {font_info}; width: 100%; }}
            .info-table td {{ padding: 2.5px 0; color: #000000; }}
        </style>
        </head>
        <body>
            <div class='receipt-container'>
                <div class='center'>
                    <div class='title'>اختبار الطباعة</div>
                    <div class='subtitle'>تجربة توافق الطباعة</div>
                </div>
                <div class='divider'></div>
                <table class='info-table'>
                    <tr><td align='right'><b>حجم الورق:</b></td><td align='left'>{paper_w} ملليمتر ({"ورق صغير" if paper_w == 58 else "ورق كبير"})</td></tr>
                    <tr><td align='right'><b>الطابعة:</b></td><td align='left'>{selected_option}</td></tr>
                    <tr><td align='right'><b>الحالة:</b></td><td align='left'>الطباعة تعمل بشكل صحيح وجاهزة ✅</td></tr>
                </table>
                <div class='divider'></div>
                <div class='center' style='font-size: {font_sub}; font-weight: bold;'>
                    الطابعة جاهزة للاستخدام
                </div>
            </div>
        </body>
        </html>
        """

        success = print_text_to_printer(test_html, self)

        # Restore config
        config.PRINTER_ONLINE = old_online
        config.SELECTED_PRINTER = old_printer
        config.PAPER_WIDTH = old_width

        if success:
            QMessageBox.information(self, "نجاح", "تم إرسال صفحة اختبار الطباعة بنجاح ✅")
        else:
            QMessageBox.critical(self, "خطأ", "تعذر طباعة الصفحة التجريبية. يرجى التحقق من اتصال الكابل أو التعريف.")

    def save_settings(self):
        selected_option = self.printer_dropdown.currentText()
        paper_w = 58 if self.radio_58.isChecked() else 80
        is_online = selected_option != "⚠️ وضع المحاكاة (تعطيل الطباعة الورقية)"
        printer_name = selected_option if is_online else ""

        # Update database settings
        try:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("UPDATE settings SET value=? WHERE key='printer_paper_width'", (str(paper_w),))
            c.execute("UPDATE settings SET value=? WHERE key='selected_printer'", (printer_name,))
            c.execute("UPDATE settings SET value=? WHERE key='printer_online'", ("1" if is_online else "0",))
            conn.commit()
            conn.close()

            # Apply to global config
            config.PAPER_WIDTH = paper_w
            config.SELECTED_PRINTER = printer_name
            config.PRINTER_ONLINE = is_online

            QMessageBox.information(self, "نجاح", "تم حفظ إعدادات الطباعة والورق بنجاح ✅")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء حفظ الإعدادات:\n{str(e)}")
            self.reject()
