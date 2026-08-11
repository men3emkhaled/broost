# -*- coding: utf-8 -*-
"""Isolated web/POS synchronization smoke test."""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QCoreApplication

import database
from core.online_sync import OnlineSyncManager


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class BroostEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="broost-e2e-")
        cls.temp_path = Path(cls.temp.name)
        cls.local_db = cls.temp_path / "pos.db"
        cls.original_db_path = database.DB_PATH
        if Path(database.DB_PATH).exists():
            shutil.copy2(database.DB_PATH, cls.local_db)
        database.DB_PATH = str(cls.local_db)
        database.init_db()

        # A clean checkout intentionally contains no restaurant database. Seed
        # one deterministic item so the end-to-end sync tests do not depend on
        # developer or production data being present on disk.
        fixture = database.get_connection()
        if not fixture.execute("SELECT 1 FROM menu_items LIMIT 1").fetchone():
            category_id = fixture.execute(
                "INSERT INTO categories (name, sort_order, sync_id) VALUES (?, ?, ?)",
                ("اختبار", 1, "test-category"),
            ).lastrowid
            fixture.execute(
                "INSERT INTO menu_items "
                "(category_id, name, base_price, is_available, is_popular, is_daily_offer, sync_id) "
                "VALUES (?, ?, ?, 1, 1, 0, ?)",
                (category_id, "وجبة اختبار", 100, "test-item"),
            )
            fixture.commit()
        fixture.close()

        # The source database may already contain real online orders. Keep this
        # smoke test deterministic by clearing them only from its temporary copy.
        isolated = database.get_connection()
        isolated.execute(
            "DELETE FROM order_items WHERE order_id IN "
            "(SELECT id FROM orders WHERE source='ONLINE')"
        )
        isolated.execute("DELETE FROM orders WHERE source='ONLINE'")
        isolated.commit()
        isolated.close()

        cls.port = free_port()
        env = os.environ.copy()
        env["BROOST_WEB_DATA_DIR"] = str(cls.temp_path / "web")
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cls.server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "webapp.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        for _ in range(60):
            try:
                cls.request("/health")
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("temporary Broost web server did not start")

        conn = database.get_connection()
        conn.executemany(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            [
                ("web_server_url", f"http://127.0.0.1:{cls.port}"),
                ("web_sync_key", "broost-local-sync"),
                ("web_sync_enabled", "1"),
                ("web_last_event_id", "0"),
                ("web_menu_version", "0"),
                ("web_menu_fingerprint", ""),
                ("web_initial_orders_synced", "0"),
            ],
        )
        conn.commit()
        conn.close()
        cls.qt_app = QCoreApplication.instance() or QCoreApplication([])
        OnlineSyncManager()._sync_menu()

    @classmethod
    def tearDownClass(cls):
        if cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server.kill()
        database.DB_PATH = cls.original_db_path
        cls.temp.cleanup()

    @classmethod
    def request(cls, path, method="GET", payload=None, admin=False, sync=False):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if admin:
            headers["X-Admin-Key"] = "9999"
        if sync:
            headers["X-Sync-Key"] = "broost-local-sync"
        request = urllib.request.Request(
            f"http://127.0.0.1:{cls.port}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}

    def test_connection_check_reports_server_key_and_sync_separately(self):
        base_url = f"http://127.0.0.1:{self.port}"

        connected = OnlineSyncManager.check_connection(
            base_url, "broost-local-sync"
        )
        self.assertTrue(connected["server_ok"])
        self.assertTrue(connected["key_ok"])
        self.assertTrue(connected["sync_ok"])

        wrong_key = OnlineSyncManager.check_connection(base_url, "wrong-key")
        self.assertTrue(wrong_key["server_ok"])
        self.assertFalse(wrong_key["key_ok"])
        self.assertFalse(wrong_key["sync_ok"])
        self.assertIn("مفتاح المزامنة", wrong_key["message"])

    def test_customer_orders_arrive_in_local_pos(self):
        manager = OnlineSyncManager()
        received = []
        manager.order_received.connect(received.append)
        manager._poll_worker()

        store = self.request("/api/store")
        self.assertTrue(store["menu"]["items"])
        item = store["menu"]["items"][0]

        # Menu edits made in the admin dashboard must reach the local POS.
        admin_menu = self.request("/api/admin/menu", admin=True)
        admin_item = next(row for row in admin_menu["items"] if row["sync_id"] == item["sync_id"])
        sizes = [
            {"name": row["name"], "price": row["price_offset"]}
            for row in admin_menu["sizes"] if row["item_sync_id"] == item["sync_id"]
        ]
        extras = [
            {"name": row["name"], "price": row["price"]}
            for row in admin_menu["extras"] if row["item_sync_id"] == item["sync_id"]
        ]
        changed_price = float(admin_item["base_price"]) + 1
        self.request(
            f"/api/admin/menu/items/{item['sync_id']}",
            "PATCH",
            {
                "category_sync_id": admin_item["category_sync_id"],
                "name": admin_item["name"],
                "base_price": changed_price,
                "is_available": bool(admin_item["is_available"]),
                "is_popular": bool(admin_item["is_popular"]),
                "sizes": sizes,
                "extras": extras,
            },
            admin=True,
        )
        manager._poll_worker()
        conn = database.get_connection()
        local_price = conn.execute(
            "SELECT base_price FROM menu_items WHERE sync_id=?",
            (item["sync_id"],),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(local_price, changed_price)

        # A subsequent local edit must travel in the other direction.
        local_changed_price = changed_price + 1
        conn = database.get_connection()
        conn.execute(
            "UPDATE menu_items SET base_price=? WHERE sync_id=?",
            (local_changed_price, item["sync_id"]),
        )
        conn.commit()
        conn.close()
        manager._poll_worker()
        remote_item = next(
            row for row in self.request("/api/store")["menu"]["items"]
            if row["sync_id"] == item["sync_id"]
        )
        self.assertEqual(remote_item["base_price"], local_changed_price)

        # A real offer can repeat one product, computes its old price, and
        # synchronizes in both directions just like the rest of the menu.
        regular_offer_price = local_changed_price * 2
        created_offer = self.request(
            "/api/admin/offers",
            "POST",
            {
                "name": "عرض برجر مزدوج اختبار",
                "offer_price": regular_offer_price - 10,
                "is_active": True,
                "items": [{"item_sync_id": item["sync_id"], "quantity": 2}],
            },
            admin=True,
        )
        manager._poll_worker()
        conn = database.get_connection()
        local_offer = conn.execute(
            "SELECT id, offer_price FROM offers WHERE sync_id=?", (created_offer["sync_id"],)
        ).fetchone()
        local_components = conn.execute(
            "SELECT menu_item_id, quantity FROM offer_items WHERE offer_id=?", (local_offer[0],)
        ).fetchall()
        self.assertEqual(local_components[0][1], 2)
        locally_changed_offer_price = float(local_offer[1]) - 1
        conn.execute(
            "UPDATE offers SET offer_price=? WHERE id=?",
            (locally_changed_offer_price, local_offer[0]),
        )
        conn.commit()
        conn.close()
        manager._poll_worker()
        public_offer = next(
            row for row in self.request("/api/store")["menu"]["offers"]
            if row["sync_id"] == created_offer["sync_id"]
        )
        self.assertEqual(public_offer["offer_price"], locally_changed_offer_price)

        area = self.request(
            "/api/admin/areas",
            "POST",
            {"name": "قرية اختبار", "delivery_fee": 35, "is_active": True, "sort_order": 1},
            admin=True,
        )
        self.request(
            "/api/admin/settings",
            "PUT",
            {"restaurant_name": "Broost", "wallet_number": "01000000000", "ordering_enabled": True},
            admin=True,
        )
        base_order = {
            "customer_name": "عميل اختبار",
            "customer_phone": "01011111111",
            "notes": "",
            "items": [
                {
                    "item_id": item["sync_id"],
                    "quantity": 1,
                    "size_id": None,
                    "extra_ids": [],
                    "spicy": False,
                }
            ],
        }
        cash = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-cash-0001",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "area_id": None,
                "detailed_address": "",
                **base_order,
            },
        )
        deal = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-offer-0001",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "customer_name": "عميل عرض اختبار",
                "customer_phone": "01022222222",
                "area_id": None,
                "detailed_address": "",
                "notes": "",
                "items": [{
                    "item_id": None,
                    "offer_id": created_offer["sync_id"],
                    "quantity": 1,
                    "size_id": None,
                    "extra_ids": [],
                    "spicy": False,
                }],
            },
        )
        self.assertEqual(deal["subtotal"], locally_changed_offer_price)
        self.assertEqual(deal["items"][0]["item_name"], "عرض: عرض برجر مزدوج اختبار")
        self.assertEqual(deal["items"][0]["extras"][0]["system_key"], "offer_component")
        cash_again = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-cash-0001",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "area_id": None,
                "detailed_address": "",
                **base_order,
            },
        )
        self.assertEqual(cash_again["public_number"], cash["public_number"])
        self.assertEqual(cash_again["resume_token"], cash["resume_token"])
        self.assertEqual(
            self.request(f"/api/orders/{cash['resume_token']}")["public_number"],
            cash["public_number"],
        )
        wallet = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-wallet-0001",
                "fulfillment": "DELIVERY",
                "payment_method": "WALLET",
                "area_id": area["id"],
                "detailed_address": "عنوان اختبار",
                **base_order,
            },
        )
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl6QAAAAASUVORK5CYII="
        )
        self.request(
            f"/api/orders/{wallet['resume_token']}/proof",
            "POST",
            {
                "filename": "proof.png",
                "mime_type": "image/png",
                "data_base64": base64.b64encode(png).decode("ascii"),
                "transfer_phone_suffix": "1111",
            },
        )

        login_profile = self.request("/api/loyalty?phone=01011111111")
        self.assertEqual(login_profile["customer"]["name"], "عميل اختبار")
        self.assertEqual(login_profile["customer"]["detailed_address"], "عنوان اختبار")
        self.assertEqual(login_profile["customer"]["area_name"], "قرية اختبار")

        manager._poll_worker()
        conn = database.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT remote_id, public_number, payment_status, source, total, delivery_fee "
            "FROM orders WHERE source='ONLINE' ORDER BY remote_id"
        ).fetchall()
        conn.close()
        expected_numbers = {cash["public_number"], deal["public_number"], wallet["public_number"]}
        rows = [row for row in rows if row["public_number"] in expected_numbers]
        wallet_row = next(row for row in rows if row["public_number"] == wallet["public_number"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(wallet_row["payment_status"], "PROOF_UPLOADED")
        self.assertEqual(wallet_row["delivery_fee"], 35)
        self.assertAlmostEqual(wallet_row["total"] - wallet_row["delivery_fee"], local_changed_price)
        self.assertEqual(sum(row.get("public_number") in expected_numbers for row in received), 3)

    def test_customer_reliability_is_advisory_and_reviews_are_real_only(self):
        store = self.request("/api/store")
        item = store["menu"]["items"][0]
        phone = "01099998888"
        created_ids = []

        for index in range(2):
            order = self.request(
                "/api/orders",
                "POST",
                {
                    "client_request_id": f"e2e-trust-{index:04d}",
                    "fulfillment": "PICKUP",
                    "payment_method": "CASH",
                    "customer_name": "عميل موثوق اختبار",
                    "customer_phone": phone,
                    "area_id": None,
                    "detailed_address": "",
                    "notes": "",
                    "items": [{
                        "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                        "extra_ids": [], "spicy": False,
                    }],
                },
            )
            remote = next(
                row for row in self.request("/api/admin/orders", admin=True)
                if row["public_number"] == order["public_number"]
            )
            self.assertEqual(
                remote["customer_reliability"]["order_mood"],
                "NEUTRAL" if index == 0 else "HAPPY",
            )
            created_ids.append(remote["id"])
            self.request(
                f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "PREPARING"}, admin=True
            )
            self.request(
                f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "COMPLETED"}, admin=True
            )

        profile = self.request(f"/api/admin/customers/{phone}", admin=True)
        self.assertEqual(profile["reliability"]["status"], "REGULAR")
        self.assertEqual(profile["reliability"]["completed_orders"], 2)

        issue_result = self.request(
            f"/api/admin/orders/{created_ids[-1]}/customer-issues",
            "POST",
            {"issue_type": "UNREACHABLE", "note": "اختبار تنبيه يدوي"},
            admin=True,
        )
        self.assertEqual(issue_result["reliability"]["status"], "NEEDS_CONFIRMATION")
        issue_id = issue_result["issues"][0]["id"]
        resolved = self.request(
            f"/api/admin/customer-issues/{issue_id}",
            "PATCH",
            {"is_resolved": True},
            admin=True,
        )
        self.assertEqual(resolved["reliability"]["status"], "REGULAR")

        returned = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-trust-returned",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "customer_name": "عميل موثوق اختبار",
                "customer_phone": phone,
                "area_id": None,
                "detailed_address": "",
                "notes": "",
                "items": [{
                    "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                    "extra_ids": [], "spicy": False,
                }],
            },
        )
        returned_remote = next(
            row for row in self.request("/api/admin/orders", admin=True)
            if row["public_number"] == returned["public_number"]
        )
        self.request(
            f"/api/admin/orders/{returned_remote['id']}",
            "PATCH",
            {"status": "CANCELLED"},
            admin=True,
        )
        after_return = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-trust-after-return",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "customer_name": "عميل موثوق اختبار",
                "customer_phone": phone,
                "area_id": None,
                "detailed_address": "",
                "notes": "",
                "items": [{
                    "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                    "extra_ids": [], "spicy": False,
                }],
            },
        )
        after_return_remote = next(
            row for row in self.request("/api/admin/orders", admin=True)
            if row["public_number"] == after_return["public_number"]
        )
        self.assertEqual(
            after_return_remote["customer_reliability"]["order_mood"], "ANGRY"
        )

        review = self.request(
            "/api/admin/reviews",
            "POST",
            {
                "customer_name": "عميل حقيقي",
                "review_text": "طلب واضح ووصل مضبوط",
                "rating": 5,
                "is_visible": True,
                "sort_order": 1,
            },
            admin=True,
        )
        public_reviews = self.request("/api/store")["reviews"]
        self.assertTrue(any(row["id"] == review["id"] for row in public_reviews))

    def test_loyalty_reward_and_exact_paid_points_are_idempotent(self):
        web_db = self.temp_path / "web" / "broost_web.db"
        reward_phone = "01077776666"
        conn = sqlite3.connect(web_db, timeout=20)
        conn.execute(
            "INSERT OR REPLACE INTO loyalty_accounts "
            "(phone_normalized, points_balance, lifetime_points, updated_at) "
            "VALUES (?, 100, 100, ?)",
            (reward_phone, "2026-08-05T12:00:00Z"),
        )
        conn.commit()
        conn.close()

        store = self.request("/api/store")
        item = min(
            (row for row in store["menu"]["items"] if 0 < float(row["base_price"]) <= 150),
            key=lambda row: float(row["base_price"]),
        )
        reward_order = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-loyalty-reward-0001",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "customer_name": "عميل نقاط اختبار",
                "customer_phone": reward_phone,
                "area_id": None,
                "detailed_address": "",
                "notes": "",
                "redeem_reward": True,
                "items": [{
                    "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                    "extra_ids": [], "spicy": False,
                }],
            },
        )
        self.assertEqual(reward_order["discount"], reward_order["subtotal"])
        self.assertEqual(reward_order["total"], 0)
        self.assertEqual(reward_order["loyalty"]["points_redeemed"], 100)
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 0)

        remote = next(
            row for row in self.request("/api/admin/orders", admin=True)
            if row["public_number"] == reward_order["public_number"]
        )
        accepted = self.request(
            f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "ACCEPTED"}, admin=True
        )
        self.assertEqual(accepted["status"], "PREPARING")
        self.request(
            f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "CANCELLED"}, admin=True
        )
        self.request(
            f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "CANCELLED"}, admin=True
        )
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 100)

        with self.assertRaises(urllib.error.HTTPError) as reopen_error:
            self.request(
                f"/api/admin/orders/{remote['id']}",
                "PATCH",
                {"status": "PREPARING"},
                admin=True,
            )
        self.assertEqual(reopen_error.exception.code, 409)

        customer_cancelled_order = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-loyalty-customer-cancel-0002",
                "fulfillment": "PICKUP",
                "payment_method": "CASH",
                "customer_name": "عميل نقاط اختبار",
                "customer_phone": reward_phone,
                "area_id": None,
                "detailed_address": "",
                "notes": "",
                "redeem_reward": True,
                "items": [{
                    "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                    "extra_ids": [], "spicy": False,
                }],
            },
        )
        cancelled = self.request(
            f"/api/orders/{customer_cancelled_order['resume_token']}/cancel", "POST"
        )
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(cancelled["cancelled_by"], "CUSTOMER")
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 100)

        cancel_updates = []
        cancel_receives = []
        manager = OnlineSyncManager()
        manager.order_updated.connect(cancel_updates.append)
        manager.order_received.connect(cancel_receives.append)
        manager._poll_worker()
        self.assertTrue(any(
            row.get("public_number") == customer_cancelled_order["public_number"]
            and row.get("_event_type") == "ORDER_CANCELLED_BY_CUSTOMER"
            for row in cancel_updates
        ))
        self.assertFalse(any(
            row.get("public_number") == customer_cancelled_order["public_number"]
            for row in cancel_receives
        ))

        # Repeating the request must be harmless: one refund and one customer alert event only.
        self.request(f"/api/orders/{customer_cancelled_order['resume_token']}/cancel", "POST")
        conn = sqlite3.connect(web_db, timeout=20)
        refund_counts = conn.execute(
            "SELECT order_id, COUNT(*) FROM loyalty_transactions "
            "WHERE transaction_type='REDEEM_REFUND' GROUP BY order_id"
        ).fetchall()
        customer_cancel_order_id = conn.execute(
            "SELECT id FROM orders WHERE public_number=?",
            (customer_cancelled_order["public_number"],),
        ).fetchone()[0]
        customer_cancel_event_count = conn.execute(
            "SELECT COUNT(*) FROM order_events WHERE order_id=? "
            "AND event_type='ORDER_CANCELLED_BY_CUSTOMER'",
            (customer_cancel_order_id,),
        ).fetchone()[0]
        conn.close()
        self.assertTrue(refund_counts)
        self.assertTrue(all(count == 1 for _, count in refund_counts))
        self.assertEqual(customer_cancel_event_count, 1)

        paid_phone = "01055554444"
        conn = sqlite3.connect(web_db, timeout=20)
        cursor = conn.execute(
            """
            INSERT INTO orders (
                public_number, resume_token, client_request_id, source, fulfillment,
                customer_name, customer_phone, customer_phone_normalized,
                payment_method, payment_status, status, subtotal, delivery_fee,
                discount, total, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 'ONLINE', 'PICKUP', ?, ?, ?, 'CASH',
                      'CASH_ON_PICKUP', 'NEW', 170, 0, 0, 170, '', ?, ?)
            """,
            (
                "WEB-LOYALTY-170", "loyalty-170-token", "e2e-loyalty-paid-0170",
                "عميل 170", paid_phone, paid_phone,
                "2026-08-05T12:00:00Z", "2026-08-05T12:00:00Z",
            ),
        )
        paid_order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.request(
            f"/api/admin/orders/{paid_order_id}", "PATCH", {"status": "PREPARING"}, admin=True
        )
        for _ in range(2):
            self.request(
                f"/api/admin/orders/{paid_order_id}", "PATCH", {"status": "COMPLETED"}, admin=True
            )
        paid_profile = self.request(f"/api/loyalty?phone={paid_phone}")
        self.assertEqual(paid_profile["points"], 17)
        self.assertEqual(paid_profile["lifetime_points"], 17)

    def test_reward_code_discount_history_and_cancelled_code_reuse(self):
        web_db = self.temp_path / "web" / "broost_web.db"
        phone = "01060606060"
        conn = sqlite3.connect(web_db, timeout=20)
        conn.execute(
            "INSERT OR REPLACE INTO loyalty_accounts "
            "(phone_normalized, points_balance, lifetime_points, updated_at) "
            "VALUES (?, 100, 100, ?)",
            (phone, "2026-08-11T10:00:00Z"),
        )
        conn.commit()
        conn.close()

        profile = self.request(
            "/api/loyalty/reward-codes", "POST", {"phone": phone}
        )
        self.assertEqual(profile["points"], 0)
        self.assertEqual(len(profile["reward_codes"]), 1)
        reward_code = profile["reward_codes"][0]["code"]

        store = self.request("/api/store")
        item = max(
            (row for row in store["menu"]["items"] if float(row["base_price"]) > 0),
            key=lambda row: float(row["base_price"]),
        )
        quantity = max(1, min(30, int(170 // float(item["base_price"])) + 1))
        area = self.request(
            "/api/admin/areas",
            "POST",
            {
                "name": "قرية كود اختبار",
                "delivery_fee": 37,
                "is_active": True,
                "delivery_enabled": True,
                "sort_order": 71,
            },
            admin=True,
        )
        order_payload = {
            "client_request_id": "e2e-reward-code-0001",
            "fulfillment": "DELIVERY",
            "payment_method": "CASH",
            "customer_name": "عميل كود اختبار",
            "customer_phone": phone,
            "area_id": area["id"],
            "detailed_address": "شارع اختبار",
            "notes": "",
            "reward_code": reward_code,
            "items": [{
                "item_id": item["sync_id"], "quantity": quantity,
                "size_id": None, "extra_ids": [], "spicy": False,
            }],
        }
        order = self.request("/api/orders", "POST", order_payload)
        self.assertGreater(order["subtotal"], 150)
        self.assertEqual(order["discount"], 150)
        self.assertEqual(order["delivery_fee"], 37)
        self.assertEqual(order["total"], round(order["subtotal"] - 150 + 37, 2))
        self.assertEqual(order["reward"]["code"], reward_code)
        self.assertEqual(order["reward"]["status"], "RESERVED")
        self.assertFalse(self.request(f"/api/loyalty?phone={phone}")["reward_codes"])

        history = self.request(f"/api/customer/orders?phone={phone}")
        self.assertEqual(history["orders"][0]["public_number"], order["public_number"])
        self.assertEqual(history["orders"][0]["discount"], 150)

        cancelled = self.request(f"/api/orders/{order['resume_token']}/cancel", "POST")
        self.assertEqual(cancelled["reward"]["status"], "ACTIVE")
        after_cancel = self.request(f"/api/loyalty?phone={phone}")
        self.assertEqual(after_cancel["points"], 0)
        self.assertEqual(after_cancel["reward_codes"][0]["code"], reward_code)

        order_payload.update({
            "client_request_id": "e2e-reward-code-0002",
            "fulfillment": "PICKUP",
            "area_id": None,
            "detailed_address": "",
        })
        reused = self.request("/api/orders", "POST", order_payload)
        remote = next(
            row for row in self.request("/api/admin/orders", admin=True)
            if row["public_number"] == reused["public_number"]
        )
        self.request(
            f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "PREPARING"}, admin=True
        )
        completed = self.request(
            f"/api/admin/orders/{remote['id']}", "PATCH", {"status": "COMPLETED"}, admin=True
        )
        self.assertEqual(completed["reward"]["status"], "USED")
        self.assertFalse(self.request(f"/api/loyalty?phone={phone}")["reward_codes"])

        order_payload["client_request_id"] = "e2e-reward-code-0003"
        with self.assertRaises(urllib.error.HTTPError) as reused_error:
            self.request("/api/orders", "POST", order_payload)
        self.assertEqual(reused_error.exception.code, 409)

    def test_delivery_area_can_pause_without_disappearing(self):
        area = self.request(
            "/api/admin/areas",
            "POST",
            {
                "name": "قرية متوقفة اختبار",
                "delivery_fee": 42,
                "is_active": True,
                "delivery_enabled": False,
                "sort_order": 72,
            },
            admin=True,
        )
        public_area = next(
            row for row in self.request("/api/store")["areas"] if row["id"] == area["id"]
        )
        self.assertEqual(public_area["delivery_fee"], 42)
        self.assertFalse(public_area["delivery_enabled"])

        item = self.request("/api/store")["menu"]["items"][0]
        payload = {
            "client_request_id": "e2e-paused-area-0001",
            "fulfillment": "DELIVERY",
            "payment_method": "CASH",
            "customer_name": "عميل قرية متوقفة",
            "customer_phone": "01070707070",
            "area_id": area["id"],
            "detailed_address": "شارع اختبار",
            "notes": "",
            "items": [{
                "item_id": item["sync_id"], "quantity": 1,
                "size_id": None, "extra_ids": [], "spicy": False,
            }],
        }
        with self.assertRaises(urllib.error.HTTPError) as paused_error:
            self.request("/api/orders", "POST", payload)
        self.assertEqual(paused_error.exception.code, 409)

        self.request(
            f"/api/admin/areas/{area['id']}",
            "PATCH",
            {"delivery_enabled": True},
            admin=True,
        )
        created = self.request("/api/orders", "POST", payload)
        self.assertEqual(created["delivery_fee"], 42)

    def test_strict_wallet_rejection_and_stale_sync_preserve_points_and_totals(self):
        manager = OnlineSyncManager()
        manager._poll_worker()
        web_db = self.temp_path / "web" / "broost_web.db"
        reward_phone = "01033332222"
        conn = sqlite3.connect(web_db, timeout=20)
        conn.execute(
            "INSERT OR REPLACE INTO loyalty_accounts "
            "(phone_normalized, points_balance, lifetime_points, updated_at) "
            "VALUES (?, 100, 100, ?)",
            (reward_phone, "2026-08-05T12:00:00Z"),
        )
        conn.commit()
        conn.close()

        self.request(
            "/api/admin/settings",
            "PUT",
            {"restaurant_name": "Broost", "wallet_number": "01000000000", "ordering_enabled": True},
            admin=True,
        )
        store = self.request("/api/store")
        item = min(
            (row for row in store["menu"]["items"] if 0 < float(row["base_price"]) <= 150),
            key=lambda row: float(row["base_price"]),
        )
        area = store["areas"][0] if store["areas"] else self.request(
            "/api/admin/areas",
            "POST",
            {"name": "قرية صرامة", "delivery_fee": 35, "is_active": True, "sort_order": 50},
            admin=True,
        )
        order = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-strict-wallet-reward-0001",
                "fulfillment": "DELIVERY",
                "payment_method": "WALLET",
                "customer_name": "عميل صرامة النقاط",
                "customer_phone": reward_phone,
                "area_id": area["id"],
                "detailed_address": "عنوان اختبار الصرامة",
                "notes": "",
                "redeem_reward": True,
                "items": [{
                    "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                    "extra_ids": [], "spicy": False,
                }],
            },
        )
        remote = next(
            row for row in self.request("/api/admin/orders", admin=True)
            if row["public_number"] == order["public_number"]
        )
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 0)

        with self.assertRaises(urllib.error.HTTPError) as unpaid_prepare:
            self.request(
                f"/api/admin/orders/{remote['id']}",
                "PATCH",
                {"status": "PREPARING"},
                admin=True,
            )
        self.assertEqual(unpaid_prepare.exception.code, 409)

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl6QAAAAASUVORK5CYII="
        )
        proof_payload = {
            "filename": "proof.png",
            "mime_type": "image/png",
            "data_base64": base64.b64encode(png).decode("ascii"),
            "transfer_phone_suffix": "2222",
        }
        self.request(f"/api/orders/{order['resume_token']}/proof", "POST", proof_payload)
        self.request(f"/api/orders/{order['resume_token']}/proof", "POST", proof_payload)
        conn = sqlite3.connect(web_db, timeout=20)
        proof_events = conn.execute(
            "SELECT COUNT(*) FROM order_events WHERE order_id=? "
            "AND event_type='PAYMENT_PROOF_UPLOADED'",
            (remote["id"],),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(proof_events, 1)

        rejected_proof = self.request(
            f"/api/admin/orders/{remote['id']}",
            "PATCH",
            {"payment_status": "REJECTED"},
            admin=True,
        )
        self.assertEqual(rejected_proof["status"], "NEW")
        self.assertEqual(rejected_proof["payment_status"], "REJECTED")
        # Rejecting only the screenshot keeps the reward reserved while the order is open.
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 0)

        cancelled = self.request(
            f"/api/admin/orders/{remote['id']}",
            "PATCH",
            {"status": "CANCELLED"},
            admin=True,
        )
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(cancelled["loyalty"]["points"], 100)
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 100)

        stale = self.request(
            "/api/sync/pos-orders",
            "POST",
            {"orders": [{
                "remote_id": remote["id"],
                "local_order_id": 987654,
                "status": "PREPARING",
                "total": 9999,
                "subtotal": 9999,
                "discount": 0,
                "delivery_fee": 0,
                "driver_name": "",
                "cashier_name": "اختبار قديم",
                "items": [],
            }]},
            sync=True,
        )
        self.assertEqual(stale["ignored"], 1)
        after_stale = self.request(f"/api/orders/{order['resume_token']}")
        self.assertEqual(after_stale["status"], "CANCELLED")
        self.assertEqual(after_stale["total"], order["total"])
        self.assertEqual(self.request(f"/api/loyalty?phone={reward_phone}")["points"], 100)

        with self.assertRaises(urllib.error.HTTPError) as closed_payment_change:
            self.request(
                f"/api/admin/orders/{remote['id']}",
                "PATCH",
                {"payment_status": "CONFIRMED"},
                admin=True,
            )
        self.assertEqual(closed_payment_change.exception.code, 409)

        conn = sqlite3.connect(web_db, timeout=20)
        refund_count = conn.execute(
            "SELECT COUNT(*) FROM loyalty_transactions WHERE order_id=? "
            "AND transaction_type='REDEEM_REFUND'",
            (remote["id"],),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(refund_count, 1)

        canonical = self.request(
            "/api/orders",
            "POST",
            {
                "client_request_id": "e2e-strict-canonical-delivery-0002",
                "fulfillment": "DELIVERY",
                "payment_method": "CASH",
                "customer_name": "عميل مسار الدليفري",
                "customer_phone": "01034343434",
                "area_id": area["id"],
                "detailed_address": "عنوان مسار الدليفري",
                "notes": "",
                "redeem_reward": False,
                "items": [{
                    "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                    "extra_ids": [], "spicy": False,
                }],
            },
        )
        canonical_remote = next(
            row for row in self.request("/api/admin/orders", admin=True)
            if row["public_number"] == canonical["public_number"]
        )
        canonical_sync = self.request(
            "/api/sync/pos-orders",
            "POST",
            {"orders": [{
                "remote_id": canonical_remote["id"],
                "local_order_id": 123456,
                "status": "NEW",
                "total": 9999,
                "subtotal": 9999,
                "discount": 0,
                "delivery_fee": 0,
                "driver_name": "",
                "cashier_name": "DR OMAR",
                "items": [],
            }]},
            sync=True,
        )
        self.assertEqual(canonical_sync["synced"], 1)
        canonical_after_sync = self.request(f"/api/orders/{canonical['resume_token']}")
        self.assertEqual(canonical_after_sync["total"], canonical["total"])
        self.assertEqual(len(canonical_after_sync["items"]), len(canonical["items"]))

        self.request(
            f"/api/admin/orders/{canonical_remote['id']}",
            "PATCH",
            {"status": "PREPARING"},
            admin=True,
        )
        with self.assertRaises(urllib.error.HTTPError) as separate_ready:
            self.request(
                f"/api/admin/orders/{canonical_remote['id']}",
                "PATCH",
                {"status": "READY"},
                admin=True,
            )
        self.assertEqual(separate_ready.exception.code, 409)
        with self.assertRaises(urllib.error.HTTPError) as dispatch_without_driver:
            self.request(
                f"/api/admin/orders/{canonical_remote['id']}",
                "PATCH",
                {"status": "DISPATCHED"},
                admin=True,
            )
        self.assertEqual(dispatch_without_driver.exception.code, 409)
        dispatched = self.request(
            f"/api/admin/orders/{canonical_remote['id']}",
            "PATCH",
            {"status": "DISPATCHED", "driver_name": "طيار اختبار"},
            admin=True,
        )
        self.assertEqual(dispatched["status"], "DISPATCHED")
        with self.assertRaises(urllib.error.HTTPError) as late_customer_cancel:
            self.request(f"/api/orders/{canonical['resume_token']}/cancel", "POST")
        self.assertEqual(late_customer_cancel.exception.code, 409)
        completed = self.request(
            f"/api/admin/orders/{canonical_remote['id']}",
            "PATCH",
            {"status": "COMPLETED"},
            admin=True,
        )
        self.assertEqual(completed["status"], "COMPLETED")

    def test_concurrent_reward_reservation_allows_only_one_order(self):
        manager = OnlineSyncManager()
        manager._poll_worker()
        web_db = self.temp_path / "web" / "broost_web.db"
        phone = "01012121212"
        conn = sqlite3.connect(web_db, timeout=20)
        conn.execute(
            "INSERT OR REPLACE INTO loyalty_accounts "
            "(phone_normalized, points_balance, lifetime_points, updated_at) "
            "VALUES (?, 100, 100, ?)",
            (phone, "2026-08-05T12:00:00Z"),
        )
        conn.commit()
        conn.close()
        item = min(
            (row for row in self.request("/api/store")["menu"]["items"] if 0 < float(row["base_price"]) <= 150),
            key=lambda row: float(row["base_price"]),
        )

        def submit(index):
            try:
                result = self.request(
                    "/api/orders",
                    "POST",
                    {
                        "client_request_id": f"e2e-concurrent-reward-{index:04d}",
                        "fulfillment": "PICKUP",
                        "payment_method": "CASH",
                        "customer_name": "عميل طلبين متزامنين",
                        "customer_phone": phone,
                        "area_id": None,
                        "detailed_address": "",
                        "notes": "",
                        "redeem_reward": True,
                        "items": [{
                            "item_id": item["sync_id"], "quantity": 1, "size_id": None,
                            "extra_ids": [], "spicy": False,
                        }],
                    },
                )
                return "ok", result
            except urllib.error.HTTPError as exc:
                return "error", exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, (1, 2)))
        self.assertEqual(sum(kind == "ok" for kind, _ in outcomes), 1)
        self.assertEqual(sum(kind == "error" and value == 409 for kind, value in outcomes), 1)
        self.assertEqual(self.request(f"/api/loyalty?phone={phone}")["points"], 0)

        successful_order = next(value for kind, value in outcomes if kind == "ok")
        self.request(f"/api/orders/{successful_order['resume_token']}/cancel", "POST")
        self.assertEqual(self.request(f"/api/loyalty?phone={phone}")["points"], 100)


if __name__ == "__main__":
    unittest.main()
