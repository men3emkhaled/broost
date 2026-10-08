"""Source-level smoke checks with an isolated SQLite database and no printing."""

import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

import database
from core import config
from dialogs.customers import CustomersAdminDialog
from dialogs.receipt import ReceiptSimDialog
from dialogs.reports import ReportsDialog
from views.dashboard import MainPOSDashboard


class OfflinePOSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="broost-offline-test-")
        self.original_db = database.DB_PATH
        self.original_backup = database.BACKUP_DIR
        database.DB_PATH = str(Path(self.folder.name) / "pos.db")
        database.BACKUP_DIR = str(Path(self.folder.name) / "backups")
        database.init_db()
        self.patches = (
            patch.object(MainPOSDashboard, "run_automated_daily_backup", lambda self: None),
            patch.object(MainPOSDashboard, "auto_detect_printer_on_startup", lambda self: None),
        )
        for item in self.patches:
            item.start()
        self.window = MainPOSDashboard()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        del self.window
        for item in reversed(self.patches):
            item.stop()
        database.DB_PATH = self.original_db
        database.BACKUP_DIR = self.original_backup
        self.folder.cleanup()

    def test_four_panels_fit_small_1366_screen_with_125_percent_scaling(self):
        # 1366x768 at 125% display scaling leaves roughly 1093x614 logical px.
        self.window.resize(1093, 614)
        self.window.stacked_widget.setCurrentWidget(self.window.pos_page)
        self.window.show()
        self.app.processEvents()
        self.window._current_cat_id = 8
        self.window.load_categories()
        self.window.load_menu_items(8)
        self.app.processEvents()
        panels = (
            self.window.categories_sidebar, self.window.center_col,
            self.window.right_col, self.window.left_col,
        )
        self.assertTrue(all(panel.isVisible() and panel.width() >= 110 for panel in panels))
        self.assertLessEqual(self.window.header_bar.sizeHint().width(), self.window.width())
        self.assertEqual(self.window.scroll_menu.verticalScrollBar().maximum(), 0)
        self.assertFalse(hasattr(self.window, "online_sync"))

    def test_local_login_opens_a_shift(self):
        self.assertEqual(self.window.stacked_widget.currentWidget(), self.window.login_page)
        for digit in "1111":
            self.window.press_key(digit)
        self.window.submit_login()
        self.assertEqual(self.window.stacked_widget.currentWidget(), self.window.pos_page)
        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM shifts WHERE closed_at IS NULL").fetchone()[0], 1)
        finally:
            conn.close()

    def test_sale_receipt_and_customer_history_work_without_network(self):
        conn = database.get_connection()
        try:
            item_id, name, price = conn.execute(
                "SELECT id, name, base_price FROM menu_items ORDER BY id LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.window.add_to_cart_direct(item_id, name, "عادي", price)
        self.window.cust_name_input.setText("Test Local Customer")
        self.window.cust_phone_input.setText("01000000000")
        self.window.paid_input.setText(str(price))
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network used")), \
             patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(ReceiptSimDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
             patch.object(config, "PRINTER_ONLINE", False):
            self.window.checkout_order()
        conn = database.get_connection()
        try:
            order = conn.execute("SELECT id, total FROM orders").fetchone()
            self.assertEqual(order[1], price)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0], 1)
        finally:
            conn.close()
        self.assertEqual(self.window.cart_items, [])
        self.assertIn(name, self.window.generate_receipt_text(order[0], "نسخة الكاشير"))
        customers = CustomersAdminDialog(self.window)
        try:
            self.assertEqual(customers.customers_table.rowCount(), 1)
            customers.show_customer_orders(0, 0)
            self.assertEqual(customers.orders_table.rowCount(), 1)
        finally:
            customers.close()
        reports = ReportsDialog(self.window)
        try:
            self.assertEqual(reports.history_table.rowCount(), 1)
        finally:
            reports.close()


if __name__ == "__main__":
    unittest.main()
