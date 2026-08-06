# -*- coding: utf-8 -*-
"""Broost POS - Receipt Preview & Print Dialog"""
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QSyntaxHighlighter
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QWidget, QFrame, QMessageBox
)
from styles import STYLE_SHEET
from core import config
from core.printing import print_text_to_printer


class ReceiptHighlighter(QSyntaxHighlighter):
    """Highlight key lines in receipt text for better readability."""

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        # ── Order ID / header line ──
        fmt_header = QTextCharFormat()
        fmt_header.setFontWeight(QFont.Weight.Black)
        fmt_header.setFontPointSize(14)
        fmt_header.setForeground(QColor("#0078d4"))
        self.rules.append((QRegularExpression(r"^.*#\d+.*$"), fmt_header))

        # ── Section separators ──
        fmt_sep = QTextCharFormat()
        fmt_sep.setForeground(QColor("#9ca3af"))
        fmt_sep.setFontPointSize(8)
        self.rules.append((QRegularExpression(r"^[=\-]{5,}$"), fmt_sep))

        # ── Total line (الإجمالي) ──
        fmt_total = QTextCharFormat()
        fmt_total.setFontWeight(QFont.Weight.Black)
        fmt_total.setFontPointSize(13)
        fmt_total.setForeground(QColor("#107c10"))
        self.rules.append((QRegularExpression(r"^.*الإجمالي.*$"), fmt_total))
        self.rules.append((QRegularExpression(r"^.*المبلغ المدفوع.*$"), fmt_total))

        # ── Item price lines ──
        fmt_price = QTextCharFormat()
        fmt_price.setFontWeight(QFont.Weight.Bold)
        fmt_price.setForeground(QColor("#374151"))
        self.rules.append((QRegularExpression(r"^.*السعر.*$"), fmt_price))

        # ── Customer info ──
        fmt_cust = QTextCharFormat()
        fmt_cust.setFontWeight(QFont.Weight.Bold)
        fmt_cust.setForeground(QColor("#111827"))
        self.rules.append((QRegularExpression(r"^.*العميل.*$"), fmt_cust))
        self.rules.append((QRegularExpression(r"^.*العنوان.*$"), fmt_cust))
        self.rules.append((QRegularExpression(r"^.*هاتف.*$"), fmt_cust))
        self.rules.append((QRegularExpression(r"^.*تليفون.*$"), fmt_cust))

        # ── Discount line ──
        fmt_disc = QTextCharFormat()
        fmt_disc.setForeground(QColor("#d97706"))
        fmt_disc.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"^.*الخصم.*$"), fmt_disc))

        # ── طلبات / items header ──
        fmt_items_hdr = QTextCharFormat()
        fmt_items_hdr.setFontWeight(QFont.Weight.Bold)
        fmt_items_hdr.setForeground(QColor("#7c3aed"))
        self.rules.append((QRegularExpression(r"^.*الطلبات.*$"), fmt_items_hdr))

        # ── Restaurant name ──
        fmt_resto = QTextCharFormat()
        fmt_resto.setFontWeight(QFont.Weight.Black)
        fmt_resto.setFontPointSize(13)
        fmt_resto.setForeground(QColor("#b45309"))
        self.rules.append((QRegularExpression(r"^.*بروست.*$"), fmt_resto))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class ReceiptSimDialog(QDialog):
    """Displays double receipts (Kitchen + Cashier) before actual hard-copy printing."""

    def __init__(self, order_id, cashier_text, kitchen_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("محاكاة طباعة الفاتورة")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(760, 560)
        self.setStyleSheet(STYLE_SHEET)

        self.order_id = order_id
        self.cashier_text = cashier_text
        self.kitchen_text = kitchen_text

        self.init_ui()

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Header ──
        hdr = QHBoxLayout()
        title = QLabel(f"🧾  معاينة فاتورة الطلب #{self.order_id}", self)
        title.setStyleSheet(
            "font-size: 17px; font-weight: 900; color: #0078d4;"
        )
        hdr.addWidget(title)
        hdr.addStretch()
        btn_x = QPushButton("✕", self)
        btn_x.setFixedSize(28, 28)
        btn_x.setStyleSheet(
            "QPushButton{background:#f3f4f6;color:#4b5563;border:1px solid #e5e7eb;"
            "border-radius:6px;font-weight:bold;font-size:14px;padding:0;}"
            "QPushButton:hover{background:#fee2e2;color:#dc2626;border-color:#fca5a5;}"
        )
        btn_x.clicked.connect(self.accept)
        hdr.addWidget(btn_x)
        root.addLayout(hdr)

        # ── Divider ──
        div = QFrame(self)
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background:#e5e7eb;max-height:1px;border:none;")
        root.addWidget(div)

        # ── Dual receipt panels ──
        dual = QHBoxLayout()
        dual.setSpacing(14)

        def make_receipt_panel(label_text, receipt_text, label_color):
            panel = QVBoxLayout()

            lbl = QLabel(label_text, self)
            lbl.setStyleSheet(
                f"font-weight: bold; color: {label_color}; font-size: 13px;"
                "padding-bottom: 4px;"
            )
            panel.addWidget(lbl)

            txt = QTextEdit(self)
            txt.setReadOnly(True)
            txt.setStyleSheet(
                "QTextEdit {"
                "  background: #fafafa;"
                "  color: #111827;"
                "  border: 1px solid #e5e7eb;"
                "  border-radius: 8px;"
                "  padding: 10px;"
                "}"
            )
            txt.setHtml(receipt_text)
            panel.addWidget(txt)
            return panel

        dual.addLayout(make_receipt_panel(
            "🧾  نسخة العميل / الكاشير", self.cashier_text, "#0078d4"
        ))
        dual.addLayout(make_receipt_panel(
            "🍳  نسخة المطبخ وتحضير الطعام", self.kitchen_text, "#d97706"
        ))

        root.addLayout(dual)

        # ── Divider ──
        div2 = QFrame(self)
        div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("background:#e5e7eb;max-height:1px;border:none;")
        root.addWidget(div2)

        # ── Action Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_done = QPushButton("✓  تم الحفظ والإغلاق", self)
        btn_done.setFixedHeight(38)
        btn_done.setStyleSheet(
            "QPushButton{background:#f3f4f6;color:#374151;border:1px solid #d1d5db;"
            "border-radius:8px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#e5e7eb;}"
        )
        btn_done.clicked.connect(self.accept)

        self.btn_reprint = QPushButton("🔁  إعادة طباعة (Reprint)", self)
        self.btn_reprint.setFixedHeight(38)
        self.btn_reprint.setStyleSheet(
            "QPushButton{background:#fef3c7;color:#b45309;border:1px solid #fde68a;"
            "border-radius:8px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#fde68a;}"
        )
        self.btn_reprint.clicked.connect(self.reprint_action)

        self.btn_hard_print = QPushButton("🖨  طباعة ورقية حقيقية", self)
        self.btn_hard_print.setFixedHeight(38)
        self.btn_hard_print.setStyleSheet(
            "QPushButton{background:#0078d4;color:white;border:none;"
            "border-radius:8px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#106ebe;}"
        )
        self.btn_hard_print.clicked.connect(self.trigger_hard_print)

        btn_row.addWidget(btn_done, stretch=2)
        btn_row.addWidget(self.btn_reprint, stretch=2)
        btn_row.addWidget(self.btn_hard_print, stretch=3)
        root.addLayout(btn_row)

    def trigger_hard_print(self):
        if not config.PRINTER_ONLINE:
            QMessageBox.critical(
                self, "خطأ بالطابعة",
                "تنبيه: تعذر إرسال الأمر!\nطابعة الفواتير غير متصلة أو انقطع اتصال الكابل."
            )
            return
        success1 = print_text_to_printer(self.cashier_text, self)
        success2 = print_text_to_printer(self.kitchen_text, self)
        if success1 and success2:
            QMessageBox.information(
                self, "طابعة النظام",
                "تم إرسال نسختي الكاشير والمطبخ للطابعة بنجاح ✅"
            )

    def reprint_action(self):
        if not config.PRINTER_ONLINE:
            QMessageBox.critical(
                self, "خطأ بالطابعة",
                "تنبيه: تعذر إرسال الأمر!\nطابعة الفواتير غير متصلة أو انقطع اتصال الكابل."
            )
            return
        success = print_text_to_printer(self.cashier_text, self)
        if success:
            QMessageBox.information(self, "طابعة النظام", "تم إعادة طباعة الفاتورة بنجاح ✅")
