# -*- coding: utf-8 -*-
"""Native customer history and control panel for the cashier application."""

from __future__ import annotations

import threading
from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import database
from core import config
from core.order_finance import cancel_and_reconcile
from styles import STYLE_SHEET


STATUS_LABELS = {
    "NEW": "جديد",
    "ACCEPTED": "جاري التجهيز",
    "PREPARING": "جاري التجهيز",
    "READY": "جاهز",
    "DISPATCHED": "خرج للتوصيل",
    "COMPLETED": "تم التسليم",
    "CANCELLED": "مرفوض / ملغي",
}


class CustomersAdminDialog(QDialog):
    """Search customers, inspect orders, and update server-enforced controls."""

    request_finished = pyqtSignal(str, object, object)

    def __init__(self, sync_manager, parent=None):
        super().__init__(parent)
        self.sync_manager = sync_manager
        self.profile: dict[str, Any] | None = None
        self._busy = False
        self.setWindowTitle("إدارة العملاء")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setMinimumSize(980, 650)
        self.resize(1080, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE_SHEET)
        self.request_finished.connect(self._finish_request)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("إدارة العملاء", self)
        title.setStyleSheet(
            "font-size: 20px; font-weight: 900; color: #9f1239; border: none;"
        )
        header.addWidget(title)
        header.addStretch()
        close_button = QPushButton("إغلاق", self)
        close_button.setFixedSize(76, 34)
        close_button.clicked.connect(self.accept)
        header.addWidget(close_button)
        root.addLayout(header)

        search_frame = QFrame(self)
        search_frame.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }"
        )
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(12, 10, 12, 10)
        self.search_input = QLineEdit(search_frame)
        self.search_input.setPlaceholderText("اكتب رقم موبايل العميل...")
        self.search_input.setMaxLength(11)
        self.search_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.search_input.returnPressed.connect(self.search_customers)
        search_layout.addWidget(self.search_input, 1)
        self.search_button = QPushButton("بحث", search_frame)
        self.search_button.setObjectName("BtnPink")
        self.search_button.setFixedWidth(100)
        self.search_button.clicked.connect(self.search_customers)
        search_layout.addWidget(self.search_button)
        root.addWidget(search_frame)

        self.message_label = QLabel("اكتب رقم الموبايل واضغط بحث.", self)
        self.message_label.setStyleSheet(
            "color: #64748b; font-size: 12px; padding: 2px; border: none;"
        )
        root.addWidget(self.message_label)

        self.customers_table = QTableWidget(self)
        self.customers_table.setColumnCount(7)
        self.customers_table.setHorizontalHeaderLabels(
            ["العميل", "الموبايل", "الحالة", "مكتمل", "ملغي", "النقاط", "فتح"]
        )
        self._configure_table(self.customers_table)
        self.customers_table.setMaximumHeight(190)
        self.customers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.customers_table.setColumnWidth(1, 130)
        self.customers_table.setColumnWidth(2, 110)
        for column in (3, 4, 5, 6):
            self.customers_table.setColumnWidth(column, 82)
        root.addWidget(self.customers_table)

        profile_frame = QFrame(self)
        profile_frame.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e2e8f0; border-radius: 10px; }"
            "QLabel { border: none; background: transparent; }"
        )
        profile_layout = QVBoxLayout(profile_frame)
        profile_layout.setContentsMargins(14, 12, 14, 12)
        profile_layout.setSpacing(10)

        profile_header = QHBoxLayout()
        self.profile_name = QLabel("لم يتم اختيار عميل", profile_frame)
        self.profile_name.setStyleSheet("font-size: 16px; font-weight: 900; color: #111827;")
        profile_header.addWidget(self.profile_name)
        self.profile_phone = QLabel("", profile_frame)
        self.profile_phone.setStyleSheet("color: #64748b; font-weight: 700;")
        self.profile_phone.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        profile_header.addWidget(self.profile_phone)
        profile_header.addStretch()
        self.profile_status = QLabel("", profile_frame)
        self.profile_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_status.setMinimumWidth(100)
        profile_header.addWidget(self.profile_status)
        profile_layout.addLayout(profile_header)

        facts_actions = QHBoxLayout()
        self.profile_facts = QLabel("اختر عميلًا لعرض طلباته.", profile_frame)
        self.profile_facts.setStyleSheet("color: #475569; font-size: 12px;")
        facts_actions.addWidget(self.profile_facts, 1)
        self.trusted_button = QPushButton("موثوق دائمًا", profile_frame)
        self.trusted_button.setEnabled(False)
        self.trusted_button.clicked.connect(self.toggle_trusted)
        facts_actions.addWidget(self.trusted_button)
        self.block_button = QPushButton("حظر العميل", profile_frame)
        self.block_button.setEnabled(False)
        self.block_button.clicked.connect(self.toggle_blocked)
        facts_actions.addWidget(self.block_button)
        profile_layout.addLayout(facts_actions)
        root.addWidget(profile_frame)

        orders_title = QLabel("طلبات العميل", self)
        orders_title.setStyleSheet("font-size: 14px; font-weight: 900; color: #111827; border: none;")
        root.addWidget(orders_title)

        self.orders_table = QTableWidget(self)
        self.orders_table.setColumnCount(7)
        self.orders_table.setHorizontalHeaderLabels(
            ["الطلب", "المصدر", "الحالة", "الإجمالي", "التاريخ", "الدفع", "حذف"]
        )
        self._configure_table(self.orders_table)
        self.orders_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.orders_table.setColumnWidth(0, 115)
        self.orders_table.setColumnWidth(1, 85)
        self.orders_table.setColumnWidth(2, 120)
        self.orders_table.setColumnWidth(3, 100)
        self.orders_table.setColumnWidth(5, 105)
        self.orders_table.setColumnWidth(6, 78)
        root.addWidget(self.orders_table, 1)

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setAlternatingRowColors(True)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.search_button.setEnabled(not busy)
        has_profile = bool(self.profile)
        self.trusted_button.setEnabled(not busy and has_profile)
        self.block_button.setEnabled(not busy and has_profile)
        if message:
            self.message_label.setText(message)

    def _run_request(self, action: str, callback: Callable[[], Any], message: str) -> None:
        if self._busy:
            return
        self._set_busy(True, message)

        def worker() -> None:
            result = None
            error = None
            try:
                result = callback()
            except Exception as exc:
                error = str(exc)
            self.request_finished.emit(action, result, error)

        threading.Thread(
            target=worker, daemon=True, name=f"customer-admin-{action}"
        ).start()

    def search_customers(self) -> None:
        query = self.search_input.text().strip()
        if query and (not query.isdigit() or len(query) < 3):
            QMessageBox.warning(self, "رقم غير صالح", "اكتب 3 أرقام على الأقل للبحث.")
            return
        self._run_request(
            "search",
            lambda: self.sync_manager.search_remote_customers(query),
            "جاري البحث عن العملاء...",
        )

    def load_customer(self, phone: str) -> None:
        self._run_request(
            "profile",
            lambda: self.sync_manager.get_remote_customer(phone),
            "جاري تحميل سجل العميل...",
        )

    def toggle_trusted(self) -> None:
        if not self.profile:
            return
        phone = self.profile["phone_normalized"]
        current = bool(self.profile.get("reliability", {}).get("force_trusted"))
        self._run_request(
            "control",
            lambda: self.sync_manager.update_remote_customer(
                phone, force_trusted=not current
            ),
            "جاري تعديل حالة الثقة...",
        )

    def toggle_blocked(self) -> None:
        if not self.profile:
            return
        phone = self.profile["phone_normalized"]
        current = bool(self.profile.get("reliability", {}).get("is_blocked"))
        verb = "إلغاء حظر" if current else "حظر"
        answer = QMessageBox.question(
            self,
            f"{verb} العميل",
            f"هل تريد {verb} الرقم {phone}؟"
            + ("" if current else "\nبعد الحظر لن يستطيع إنشاء طلب جديد من الموقع."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_request(
            "control",
            lambda: self.sync_manager.update_remote_customer(phone, is_blocked=not current),
            "جاري تعديل حالة الحظر...",
        )

    def delete_order(self, order: dict[str, Any]) -> None:
        answer = QMessageBox.question(
            self,
            "حذف الطلب نهائيًا",
            f"حذف الطلب {order.get('public_number')} نهائيًا؟\n"
            "سيتم تسوية نقاط العميل والكود ثم حذف الطلب من الموقع والسيستم.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_request(
            "delete",
            lambda: self.sync_manager.delete_remote_customer_order(int(order["id"])),
            "جاري حذف الطلب وتسوية حساب العميل...",
        )

    def _finish_request(self, action: str, result: object, error: object) -> None:
        self._set_busy(False)
        if error:
            self.message_label.setText("تعذر إتمام العملية.")
            if action == "profile" and "لا يوجد عميل" in str(error):
                self._clear_profile("تم حذف آخر طلب مسجل لهذا العميل.")
                return
            QMessageBox.critical(self, "تعذر إتمام العملية", str(error))
            return

        if action == "search":
            customers = result if isinstance(result, list) else []
            self._render_customers(customers)
            self.message_label.setText(f"تم العثور على {len(customers)} عميل.")
            query = self.search_input.text().strip()
            exact = next(
                (row for row in customers if row.get("phone_normalized") == query), None
            )
            if exact:
                self.load_customer(exact["phone_normalized"])
        elif action in ("profile", "control"):
            self.profile = result if isinstance(result, dict) else None
            self._render_profile()
            self.message_label.setText("تم تحميل سجل العميل.")
        elif action == "delete":
            metadata = result if isinstance(result, dict) else {}
            self._delete_local_copy(metadata)
            parent = self.parent()
            if parent and hasattr(parent, "load_pending_delivery_orders"):
                parent.load_pending_delivery_orders()
            if parent and hasattr(parent, "ensure_active_shift"):
                parent.ensure_active_shift()
            phone = self.profile.get("phone_normalized") if self.profile else ""
            self.message_label.setText("تم حذف الطلب وتسوية حساب العميل.")
            self.profile = None
            if phone:
                self.load_customer(phone)

    def _render_customers(self, customers: list[dict[str, Any]]) -> None:
        self.customers_table.setRowCount(len(customers))
        for row_index, customer in enumerate(customers):
            values = [
                customer.get("customer_name") or "عميل",
                customer.get("customer_phone") or "",
                customer.get("label") or "عميل جديد",
                str(int(customer.get("completed_orders", 0) or 0)),
                str(int(customer.get("cancelled_orders", 0) or 0)),
                str(int(customer.get("loyalty_points", 0) or 0)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.customers_table.setItem(row_index, column, item)
            open_button = QPushButton("عرض", self.customers_table)
            phone = customer.get("phone_normalized") or customer.get("customer_phone") or ""
            open_button.clicked.connect(lambda checked=False, p=phone: self.load_customer(p))
            self.customers_table.setCellWidget(row_index, 6, self._button_cell(open_button))

    def _render_profile(self) -> None:
        if not self.profile:
            return
        reliability = self.profile.get("reliability") or {}
        loyalty = self.profile.get("loyalty") or {}
        self.profile_name.setText(self.profile.get("customer_name") or "عميل")
        self.profile_phone.setText(self.profile.get("customer_phone") or "")
        self.profile_status.setText(reliability.get("label") or "عميل جديد")
        if reliability.get("is_blocked"):
            status_style = "background:#fee2e2;color:#991b1b;border:1px solid #ef4444;"
        elif reliability.get("status") == "RELIABLE":
            status_style = "background:#dcfce7;color:#166534;border:1px solid #22c55e;"
        else:
            status_style = "background:#fff7df;color:#854d0e;border:1px solid #eab308;"
        self.profile_status.setStyleSheet(
            status_style + "border-radius:9px;padding:6px 10px;font-weight:900;"
        )
        self.profile_facts.setText(
            f"{int(reliability.get('completed_orders', 0) or 0)} طلب مكتمل  •  "
            f"{int(reliability.get('cancelled_orders', 0) or 0)} ملغي  •  "
            f"{int(loyalty.get('points', 0) or 0)} نقطة"
        )
        trusted = bool(reliability.get("force_trusted"))
        blocked = bool(reliability.get("is_blocked"))
        self.trusted_button.setText("إلغاء موثوق دائمًا" if trusted else "موثوق دائمًا")
        self.block_button.setText("إلغاء الحظر" if blocked else "حظر العميل")
        self.trusted_button.setEnabled(not self._busy)
        self.block_button.setEnabled(not self._busy)
        self._render_orders(self.profile.get("orders") or [])

    def _render_orders(self, orders: list[dict[str, Any]]) -> None:
        self.orders_table.setRowCount(len(orders))
        for row_index, order in enumerate(orders):
            payment = "نقدي" if order.get("payment_method") == "CASH" else "محفظة"
            created = str(order.get("created_at") or "").replace("T", " ")[:16]
            values = [
                order.get("public_number") or f"#{order.get('id')}",
                "الموقع" if order.get("source") == "ONLINE" else "المطعم",
                STATUS_LABELS.get(order.get("status"), str(order.get("status") or "")),
                f"{float(order.get('total', 0) or 0):,.2f} ج",
                created,
                payment,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.orders_table.setItem(row_index, column, item)
            delete_button = QPushButton("حذف", self.orders_table)
            delete_button.setStyleSheet(
                "QPushButton { background:#fee2e2;color:#991b1b;border:1px solid #fecaca;"
                "border-radius:6px;padding:5px;font-weight:800; }"
                "QPushButton:hover { background:#dc2626;color:white; }"
            )
            delete_button.clicked.connect(
                lambda checked=False, current=order: self.delete_order(current)
            )
            self.orders_table.setCellWidget(row_index, 6, self._button_cell(delete_button))

    @staticmethod
    def _button_cell(button: QPushButton) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(button)
        return cell

    @staticmethod
    def _delete_local_copy(metadata: dict[str, Any]) -> None:
        source = metadata.get("source")
        conn = database.get_connection()
        try:
            if source == "ONLINE":
                rows = conn.execute(
                    "SELECT id FROM orders WHERE remote_id=?", (metadata.get("id"),)
                ).fetchall()
            else:
                local_id = metadata.get("local_order_id")
                rows = conn.execute(
                    "SELECT id FROM orders WHERE id=?", (local_id,)
                ).fetchall() if local_id else []
            order_ids = [int(row[0]) for row in rows]
            for order_id in order_ids:
                cancel_and_reconcile(
                    conn, order_id, fallback_shift_id=config.ACTIVE_SHIFT_ID
                )
                conn.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
                conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
            conn.commit()
        finally:
            conn.close()

    def _clear_profile(self, message: str) -> None:
        self.profile = None
        self.profile_name.setText("لا توجد طلبات مسجلة")
        self.profile_phone.clear()
        self.profile_status.clear()
        self.profile_facts.setText(message)
        self.trusted_button.setEnabled(False)
        self.block_button.setEnabled(False)
        self.orders_table.setRowCount(0)
