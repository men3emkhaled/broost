# -*- coding: utf-8 -*-
"""Local customer and invoice history for the offline cashier."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

import database
from styles import STYLE_SHEET


class CustomersAdminDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("العملاء والفواتير المحلية")
        self.setMinimumSize(850, 520)
        self.resize(1020, 640)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE_SHEET)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("العملاء والفواتير المحفوظة على الجهاز"))
        header.addStretch()
        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(self.accept)
        header.addWidget(close_button)
        layout.addLayout(header)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("بحث بالاسم أو رقم الهاتف")
        self.search_input.textChanged.connect(self.load_customers)
        layout.addWidget(self.search_input)

        self.customers_table = QTableWidget(self)
        self.customers_table.setColumnCount(4)
        self.customers_table.setHorizontalHeaderLabels(
            ["العميل", "الهاتف", "الفواتير", "الإجمالي"]
        )
        self.customers_table.verticalHeader().hide()
        self.customers_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.customers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.customers_table.cellClicked.connect(self.show_customer_orders)
        layout.addWidget(self.customers_table, 2)

        self.orders_label = QLabel("اختر عميلًا لعرض فواتيره", self)
        layout.addWidget(self.orders_label)
        self.orders_table = QTableWidget(self)
        self.orders_table.setColumnCount(5)
        self.orders_table.setHorizontalHeaderLabels(
            ["رقم الفاتورة", "التاريخ", "الحالة", "طريقة الدفع", "الإجمالي"]
        )
        self.orders_table.verticalHeader().hide()
        self.orders_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.orders_table, 3)
        self.customer_ids = []
        self.load_customers()

    @staticmethod
    def _put(table, row, values):
        for column, value in enumerate(values):
            cell = QTableWidgetItem(str(value))
            cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, column, cell)

    def load_customers(self):
        query = self.search_input.text().strip()
        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT c.id, COALESCE(c.name, ''), COALESCE(c.phone, ''), "
                "COUNT(o.id), COALESCE(SUM(o.total), 0) "
                "FROM customers c LEFT JOIN orders o ON o.customer_id=c.id "
                "WHERE (?='' OR c.name LIKE ? OR c.phone LIKE ?) "
                "GROUP BY c.id ORDER BY c.id DESC LIMIT 500",
                (query, f"%{query}%", f"%{query}%"),
            ).fetchall()
        finally:
            conn.close()
        self.customer_ids = [row[0] for row in rows]
        self.customers_table.setRowCount(len(rows))
        for index, (_, name, phone, count, total) in enumerate(rows):
            self._put(self.customers_table, index,
                      (name or "عميل", phone, count, f"{total:,.2f} ج.م"))
        self.orders_table.setRowCount(0)
        self.orders_label.setText("اختر عميلًا لعرض فواتيره")

    def show_customer_orders(self, row, _column):
        if row >= len(self.customer_ids):
            return
        customer_id = self.customer_ids[row]
        conn = database.get_connection()
        try:
            orders = conn.execute(
                "SELECT COALESCE(public_number, CAST(id AS TEXT)), created_at, "
                "status, payment_method, COALESCE(total, 0) "
                "FROM orders WHERE customer_id=? ORDER BY id DESC LIMIT 500",
                (customer_id,),
            ).fetchall()
        finally:
            conn.close()
        name = self.customers_table.item(row, 0).text()
        self.orders_label.setText(f"فواتير {name}: {len(orders)}")
        self.orders_table.setRowCount(len(orders))
        for index, (number, date, status, payment, total) in enumerate(orders):
            self._put(self.orders_table, index,
                      (number, date or "", status or "", payment or "",
                       f"{total:,.2f} ج.م"))
