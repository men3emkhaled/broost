# -*- coding: utf-8 -*-
"""Background synchronization between the local POS database and Broost web API."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

import database
from core import config
from core.time_utils import to_local_db_timestamp


def strip_area_prefix(address: str | None, area_name: str | None) -> str:
    """Prevent village names from accumulating during the web/POS round trip."""
    result = (address or "").strip()
    area = (area_name or "").strip()
    if not result or not area:
        return result
    prefix = re.compile(
        rf"^\s*{re.escape(area)}(?:\s*[-–—,:،]\s*|\s+|$)",
        re.IGNORECASE,
    )
    while result and prefix.match(result):
        result = prefix.sub("", result, count=1).strip()
    return re.sub(r"^\s*[-–—,:،]+\s*", "", result).strip()


class OnlineSyncManager(QObject):
    connectivity_changed = pyqtSignal(bool, str)
    order_received = pyqtSignal(dict)
    order_updated = pyqtSignal(dict)
    menu_applied = pyqtSignal()
    sync_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy_lock = threading.Lock()
        self._last_connected: bool | None = None
        self._last_connection_message = ""
        self._last_orders_push = 0.0

    def poll(self) -> None:
        if self._busy_lock.locked():
            return
        threading.Thread(target=self._poll_worker, daemon=True, name="broost-web-sync").start()

    def push_remote_update(self, remote_id: int, **changes: Any) -> None:
        def worker():
            try:
                self._request_json(f"/api/sync/orders/{remote_id}", method="PATCH", payload=changes)
                self._set_connected(True, "متزامن أونلاين")
            except Exception as exc:
                self._set_connected(False, str(exc))

        threading.Thread(target=worker, daemon=True, name="broost-order-update").start()

    def update_remote_order_now(self, remote_id: int, **changes: Any) -> dict[str, Any]:
        """Apply a critical remote update before changing local financial state."""
        result = self._request_json(
            f"/api/sync/orders/{remote_id}", method="PATCH", payload=changes
        )
        self._set_connected(True, "متزامن أونلاين")
        return result

    def _poll_worker(self) -> None:
        if not self._busy_lock.acquire(blocking=False):
            return
        try:
            settings = self._settings()
            if settings.get("web_sync_enabled", "1") != "1":
                self._set_connected(False, "مزامنة الموقع متوقفة")
                return
            self._sync_menu()
            self._pull_events()
            if time.monotonic() - self._last_orders_push >= 20:
                self._push_pos_orders()
                self._last_orders_push = time.monotonic()
            self._set_connected(True, "متزامن أونلاين")
        except Exception as exc:
            self._set_connected(False, f"غير متصل: {exc}")
        finally:
            self._busy_lock.release()

    def _settings(self) -> dict[str, str]:
        conn = database.get_connection()
        try:
            return dict(conn.execute(
                "SELECT key, value FROM settings WHERE key LIKE 'web_%'"
            ).fetchall())
        finally:
            conn.close()

    def _setting(self, key: str, default: str = "") -> str:
        conn = database.get_connection()
        try:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default
        finally:
            conn.close()

    def _set_setting(self, key: str, value: Any) -> None:
        conn = database.get_connection()
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            conn.commit()
        finally:
            conn.close()

    def _connection_values(self) -> tuple[str, str]:
        settings = self._settings()
        base_url = settings.get("web_server_url", "http://127.0.0.1:8765").strip().rstrip("/")
        sync_key = settings.get("web_sync_key", "broost-local-sync").strip()
        return base_url, sync_key

    @staticmethod
    def check_connection(base_url: str, sync_key: str, timeout: int = 10) -> dict[str, Any]:
        """Diagnose server reachability, credentials and the sync endpoint separately."""
        base_url = (base_url or "").strip().rstrip("/")
        sync_key = (sync_key or "").strip()
        result: dict[str, Any] = {
            "server_ok": False,
            "key_ok": False,
            "sync_ok": False,
            "message": "",
            "http_status": None,
            "menu_version": 0,
            "categories": 0,
            "items": 0,
        }
        if not base_url or not sync_key:
            result["message"] = "رابط السيرفر ومفتاح المزامنة مطلوبان."
            return result

        def request(path: str, authenticated: bool = False) -> tuple[int | None, Any, str]:
            headers = {"Accept": "application/json"}
            if authenticated:
                headers["X-Sync-Key"] = sync_key
            web_request = urllib.request.Request(
                f"{base_url}{path}", method="GET", headers=headers
            )
            try:
                with urllib.request.urlopen(web_request, timeout=timeout) as response:
                    raw = response.read()
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                    return response.status, payload, ""
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                try:
                    detail = str(json.loads(raw).get("detail", raw))
                except json.JSONDecodeError:
                    detail = raw
                return exc.code, None, detail.strip()
            except urllib.error.URLError:
                return None, None, "تعذر الوصول إلى السيرفر."
            except Exception as exc:
                return None, None, str(exc)

        health_status, health, health_detail = request("/health")
        if health_status != 200 or not isinstance(health, dict) or health.get("status") != "ok":
            result["http_status"] = health_status
            result["message"] = health_detail or "السيرفر لا يستجيب بشكل صحيح."
            return result
        result["server_ok"] = True

        sync_status, menu, sync_detail = request("/api/sync/menu", authenticated=True)
        result["http_status"] = sync_status
        if sync_status in (401, 403):
            result["message"] = "السيرفر متصل، لكن مفتاح المزامنة غير صحيح."
            return result
        if sync_status is not None and sync_status >= 500:
            # The authentication dependency runs before the endpoint, so a 5xx
            # here means the supplied key was accepted and the backend failed.
            result["key_ok"] = True
            result["message"] = (
                f"السيرفر متصل والمفتاح صحيح، لكن مسار المزامنة به خطأ داخلي (HTTP {sync_status}). "
                "انشر أحدث نسخة من Railway ثم أعد الفحص."
            )
            return result
        if sync_status != 200 or not isinstance(menu, dict):
            result["message"] = sync_detail or "السيرفر متصل لكن مسار المزامنة لم يستجب."
            return result

        result.update(
            key_ok=True,
            sync_ok=True,
            menu_version=int(menu.get("version", 0) or 0),
            categories=len(menu.get("categories", [])),
            items=len(menu.get("items", [])),
        )
        if result["categories"] or result["items"]:
            result["message"] = (
                f"الاتصال والمزامنة يعملان — {result['categories']} تصنيف و"
                f" {result['items']} صنف على الموقع."
            )
        else:
            result["message"] = (
                "الاتصال والمفتاح صحيحان، والمنيو على السيرفر فارغة حاليًا. "
                "اضغط «حفظ ومزامنة الآن» لرفع بيانات الكاشير."
            )
        return result

    def _request_json(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> Any:
        base_url, sync_key = self._connection_values()
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Sync-Key": sync_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=7) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("detail", raw)
            except json.JSONDecodeError:
                detail = raw
            if exc.code in (401, 403):
                message = "مفتاح المزامنة غير صحيح"
            elif exc.code >= 500:
                message = f"السيرفر متصل لكن المزامنة بها خطأ داخلي (HTTP {exc.code})"
            else:
                message = str(detail) or f"HTTP {exc.code}"
            raise RuntimeError(message) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("السيرفر غير متاح") from exc

    def _request_bytes(self, path: str) -> bytes:
        base_url, sync_key = self._connection_values()
        request = urllib.request.Request(
            f"{base_url}{path}",
            method="GET",
            headers={"X-Sync-Key": sync_key},
        )
        with urllib.request.urlopen(request, timeout=7) as response:
            return response.read()

    def _set_connected(self, connected: bool, message: str) -> None:
        if connected != self._last_connected or message != self._last_connection_message:
            self._last_connected = connected
            self._last_connection_message = message
            self.connectivity_changed.emit(connected, message)
        elif not connected:
            self.sync_error.emit(message)

    def _menu_snapshot(self) -> dict[str, Any]:
        conn = database.get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            categories = [dict(row) for row in conn.execute(
                "SELECT id AS local_id, sync_id, name, sort_order, 1 AS is_active, 0 AS is_deleted "
                "FROM categories ORDER BY sort_order, id"
            )]
            items = [dict(row) for row in conn.execute(
                """
                SELECT m.id AS local_id, m.sync_id, c.sync_id AS category_sync_id,
                       m.name, m.base_price, m.is_available, m.is_popular,
                       m.is_daily_offer, 0 AS is_deleted
                FROM menu_items m JOIN categories c ON c.id=m.category_id
                ORDER BY m.id
                """
            )]
            sizes = [dict(row) for row in conn.execute(
                """
                SELECT s.id AS local_id, s.sync_id, m.sync_id AS item_sync_id,
                       s.name, s.price_offset
                FROM menu_item_sizes s JOIN menu_items m ON m.id=s.item_id
                ORDER BY s.id
                """
            )]
            extras = [dict(row) for row in conn.execute(
                """
                SELECT e.id AS local_id, e.sync_id, m.sync_id AS item_sync_id,
                       e.name, e.price
                FROM menu_item_extras e JOIN menu_items m ON m.id=e.item_id
                ORDER BY e.id
                """
            )]
            offers = [dict(row) for row in conn.execute(
                "SELECT id AS local_id, sync_id, name, offer_price, is_active, 0 AS is_deleted "
                "FROM offers ORDER BY id"
            )]
            offer_items = [dict(row) for row in conn.execute(
                """
                SELECT oi.id AS local_id, oi.sync_id, o.sync_id AS offer_sync_id,
                       m.sync_id AS item_sync_id, oi.quantity
                FROM offer_items oi
                JOIN offers o ON o.id=oi.offer_id
                JOIN menu_items m ON m.id=oi.menu_item_id
                ORDER BY oi.id
                """
            )]
            return {
                "categories": categories,
                "items": items,
                "sizes": sizes,
                "extras": extras,
                "offers": offers,
                "offer_items": offer_items,
            }
        finally:
            conn.close()

    @staticmethod
    def _fingerprint(snapshot: dict[str, Any]) -> str:
        compact = {
            key: snapshot.get(key, [])
            for key in ("categories", "items", "sizes", "extras", "offers", "offer_items")
        }
        raw = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _sync_menu(self) -> None:
        remote = self._request_json("/api/sync/menu")
        local = self._menu_snapshot()
        local_fingerprint = self._fingerprint(local)
        stored_fingerprint = self._setting("web_menu_fingerprint", "")
        stored_version = int(self._setting("web_menu_version", "0") or 0)
        remote_version = int(remote.get("version", 0))
        remote_has_menu = bool(remote.get("categories"))

        if not remote_has_menu:
            result = self._request_json(
                "/api/sync/menu",
                method="POST",
                payload={"known_server_version": remote_version, **local},
            )
            if result.get("accepted"):
                self._set_setting("web_menu_version", result["version"])
                self._set_setting("web_menu_fingerprint", local_fingerprint)
            return

        if remote_version != stored_version:
            self._apply_remote_menu(remote)
            return

        if local_fingerprint != stored_fingerprint:
            result = self._request_json(
                "/api/sync/menu",
                method="POST",
                payload={"known_server_version": stored_version, **local},
            )
            if result.get("accepted"):
                self._set_setting("web_menu_version", result["version"])
                self._set_setting("web_menu_fingerprint", local_fingerprint)
            elif result.get("reason") == "VERSION_CONFLICT":
                self._apply_remote_menu(result)

    def _apply_remote_menu(self, remote: dict[str, Any]) -> None:
        conn = database.get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            cursor = conn.cursor()
            remote_categories = remote.get("categories", [])
            remote_items = remote.get("items", [])
            remote_offers = remote.get("offers", [])

            # Offers are a small, full snapshot. Replacing them avoids stale
            # bundle components when either the website or cashier edits one.
            cursor.execute("DELETE FROM offer_items")
            cursor.execute("DELETE FROM offers")

            for item in remote_items:
                if not item.get("is_deleted"):
                    continue
                row = cursor.execute("SELECT id FROM menu_items WHERE sync_id=?", (item["sync_id"],)).fetchone()
                if row:
                    cursor.execute("DELETE FROM menu_item_sizes WHERE item_id=?", (row["id"],))
                    cursor.execute("DELETE FROM menu_item_extras WHERE item_id=?", (row["id"],))
                    cursor.execute("DELETE FROM menu_items WHERE id=?", (row["id"],))

            for category in remote_categories:
                if category.get("is_deleted"):
                    row = cursor.execute("SELECT id FROM categories WHERE sync_id=?", (category["sync_id"],)).fetchone()
                    if row:
                        cursor.execute("DELETE FROM menu_items WHERE category_id=?", (row["id"],))
                        cursor.execute("DELETE FROM categories WHERE id=?", (row["id"],))

            category_map: dict[str, int] = {}
            for category in remote_categories:
                if category.get("is_deleted"):
                    continue
                row = cursor.execute("SELECT id FROM categories WHERE sync_id=?", (category["sync_id"],)).fetchone()
                if not row:
                    row = cursor.execute("SELECT id FROM categories WHERE name=?", (category["name"],)).fetchone()
                    if row:
                        cursor.execute("UPDATE categories SET sync_id=? WHERE id=?", (category["sync_id"], row["id"]))
                if row:
                    local_id = row["id"]
                    cursor.execute(
                        "UPDATE categories SET name=?, sort_order=? WHERE id=?",
                        (category["name"], int(category.get("sort_order", 0)), local_id),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO categories (name, sort_order, sync_id) VALUES (?, ?, ?)",
                        (category["name"], int(category.get("sort_order", 0)), category["sync_id"]),
                    )
                    local_id = cursor.lastrowid
                category_map[category["sync_id"]] = local_id

            item_map: dict[str, int] = {}
            for item in remote_items:
                if item.get("is_deleted") or item["category_sync_id"] not in category_map:
                    continue
                row = cursor.execute("SELECT id FROM menu_items WHERE sync_id=?", (item["sync_id"],)).fetchone()
                if not row:
                    row = cursor.execute("SELECT id FROM menu_items WHERE name=?", (item["name"],)).fetchone()
                    if row:
                        cursor.execute("UPDATE menu_items SET sync_id=? WHERE id=?", (item["sync_id"], row["id"]))
                values = (
                    category_map[item["category_sync_id"]], item["name"], float(item.get("base_price", 0)),
                    int(item.get("is_available", 1)), int(item.get("is_popular", 0)),
                    int(item.get("is_daily_offer", 0)),
                )
                if row:
                    local_id = row["id"]
                    cursor.execute(
                        "UPDATE menu_items SET category_id=?, name=?, base_price=?, is_available=?, "
                        "is_popular=?, is_daily_offer=? WHERE id=?",
                        (*values, local_id),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO menu_items (category_id, name, base_price, is_available, is_popular, "
                        "is_daily_offer, sync_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (*values, item["sync_id"]),
                    )
                    local_id = cursor.lastrowid
                item_map[item["sync_id"]] = local_id

            for item_id in item_map.values():
                cursor.execute("DELETE FROM menu_item_sizes WHERE item_id=?", (item_id,))
                cursor.execute("DELETE FROM menu_item_extras WHERE item_id=?", (item_id,))
            for size in remote.get("sizes", []):
                item_id = item_map.get(size["item_sync_id"])
                if item_id:
                    cursor.execute(
                        "INSERT INTO menu_item_sizes (item_id, name, price_offset, sync_id) VALUES (?, ?, ?, ?)",
                        (item_id, size["name"], float(size.get("price_offset", 0)), size["sync_id"]),
                    )
            for extra in remote.get("extras", []):
                item_id = item_map.get(extra["item_sync_id"])
                if item_id:
                    cursor.execute(
                        "INSERT INTO menu_item_extras (item_id, name, price, sync_id) VALUES (?, ?, ?, ?)",
                        (item_id, extra["name"], float(extra.get("price", 0)), extra["sync_id"]),
                    )

            offer_map: dict[str, int] = {}
            for offer in remote_offers:
                if offer.get("is_deleted"):
                    continue
                cursor.execute(
                    "INSERT INTO offers (sync_id, name, offer_price, is_active) VALUES (?, ?, ?, ?)",
                    (
                        offer["sync_id"], offer["name"], float(offer.get("offer_price", 0)),
                        int(offer.get("is_active", 1)),
                    ),
                )
                offer_map[offer["sync_id"]] = cursor.lastrowid
            for component in remote.get("offer_items", []):
                offer_id = offer_map.get(component["offer_sync_id"])
                item_id = item_map.get(component["item_sync_id"])
                if offer_id and item_id:
                    cursor.execute(
                        "INSERT INTO offer_items "
                        "(sync_id, offer_id, menu_item_id, quantity) VALUES (?, ?, ?, ?)",
                        (
                            component["sync_id"], offer_id, item_id,
                            int(component.get("quantity", 1)),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

        snapshot = self._menu_snapshot()
        self._set_setting("web_menu_version", int(remote.get("version", 0)))
        self._set_setting("web_menu_fingerprint", self._fingerprint(snapshot))
        self.menu_applied.emit()

    def _pull_events(self) -> None:
        last_event_id = int(self._setting("web_last_event_id", "0") or 0)
        result = self._request_json(f"/api/sync/events?after={last_event_id}")
        events = result.get("events", [])
        latest_by_order: dict[int, dict[str, Any]] = {}
        for event in events:
            if event.get("order") and event["order"].get("source") == "ONLINE":
                latest_by_order[int(event["order_id"])] = event

        for event in latest_by_order.values():
            order = event["order"]
            order["_event_type"] = event.get("event_type", "")
            was_new = self._import_online_order(order)
            if order.get("has_payment_proof"):
                try:
                    order["proof_bytes"] = self._request_bytes(f"/api/sync/orders/{order['id']}/proof")
                except Exception:
                    order["proof_bytes"] = b""
            if event.get("event_type") == "ORDER_CANCELLED_BY_CUSTOMER":
                self.order_updated.emit(order)
            elif was_new:
                self.order_received.emit(order)
            else:
                self.order_updated.emit(order)

        if events:
            self._set_setting("web_last_event_id", int(result.get("last_event_id", last_event_id)))

    @staticmethod
    def _local_timestamp(value: str | None) -> str | None:
        return to_local_db_timestamp(value)

    @staticmethod
    def _local_status(remote_status: str) -> str:
        return {
            "DISPATCHED": "DISPATCHED",
            "COMPLETED": "COMPLETED",
            "CANCELLED": "CANCELLED",
        }.get(remote_status, "PENDING")

    def _import_online_order(self, order: dict[str, Any]) -> bool:
        conn = database.get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            cursor = conn.cursor()
            existing = cursor.execute("SELECT id FROM orders WHERE remote_id=?", (order["id"],)).fetchone()
            was_new = existing is None
            address = strip_area_prefix(order.get("detailed_address"), order.get("area_name"))
            phone = (order.get("customer_phone") or "").strip()
            customer = cursor.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone() if phone else None
            if customer:
                customer_id = customer["id"]
                cursor.execute(
                    "UPDATE customers SET name=?, address=? WHERE id=?",
                    (order.get("customer_name") or "عميل أونلاين", address, customer_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO customers (phone, name, address) VALUES (?, ?, ?)",
                    (phone or None, order.get("customer_name") or "عميل أونلاين", address),
                )
                customer_id = cursor.lastrowid

            channel = "DELIVERY" if order.get("fulfillment") == "DELIVERY" else "CASHIER"
            payment_method = order.get("payment_method", "CASH")
            local_status = self._local_status(order.get("status", "NEW"))
            cash_paid = float(order.get("total", 0)) if payment_method != "CASH" else 0.0
            reliability = order.get("customer_reliability") or {}
            values = (
                customer_id, channel, payment_method, float(order.get("subtotal", 0)),
                float(order.get("delivery_fee", 0)), float(order.get("discount", 0)),
                float(order.get("total", 0)), cash_paid, 0.0, local_status,
                config.ACTIVE_SHIFT_ID, order.get("notes") or "",
                self._local_timestamp(order.get("created_at")), self._local_timestamp(order.get("closed_at")),
                "ONLINE", int(order["id"]), order.get("public_number"), order.get("status"),
                order.get("payment_status"), order.get("area_name") or "",
                int(bool(order.get("has_payment_proof"))),
                reliability.get("status") or "NEW",
                int(reliability.get("completed_orders", 0) or 0),
                int(reliability.get("open_issues", 0) or 0),
                int(reliability.get("confirmed_wallets", 0) or 0),
            )
            if existing:
                local_order_id = existing["id"]
                cursor.execute(
                    """
                    UPDATE orders SET customer_id=?, channel=?, payment_method=?, subtotal=?, delivery_fee=?,
                        discount=?, total=?, cash_paid=?, change_due=?, status=?, shift_id=COALESCE(shift_id, ?),
                        notes=?, created_at=?, closed_at=?, source=?, remote_id=?, public_number=?,
                        online_status=?, payment_status=?, area_name=?, proof_available=?,
                        customer_trust_status=?, customer_completed_orders=?, customer_issue_count=?,
                        customer_confirmed_wallets=?
                    WHERE id=?
                    """,
                    (*values, local_order_id),
                )
                cursor.execute("DELETE FROM order_items WHERE order_id=?", (local_order_id,))
            else:
                cursor.execute(
                    """
                    INSERT INTO orders (
                        customer_id, channel, payment_method, subtotal, delivery_fee, discount, total,
                        cash_paid, change_due, status, shift_id, notes, created_at, closed_at, source,
                        remote_id, public_number, online_status, payment_status, area_name, proof_available
                        , customer_trust_status, customer_completed_orders, customer_issue_count,
                        customer_confirmed_wallets
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                local_order_id = cursor.lastrowid

            for item in order.get("items", []):
                menu_row = cursor.execute(
                    "SELECT id FROM menu_items WHERE sync_id=?", (item.get("menu_item_sync_id"),)
                ).fetchone()
                extras_dict: dict[str, Any] = {}
                for extra in item.get("extras", []):
                    if extra.get("system_key") == "spicy":
                        extras_dict["__spicy__"] = True
                    else:
                        extras_dict[extra.get("name", "إضافة")] = float(extra.get("price", 0))
                cursor.execute(
                    """
                    INSERT INTO order_items (
                        order_id, menu_item_id, item_name, size_name, quantity, price, extras_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        local_order_id, menu_row["id"] if menu_row else None,
                        item.get("item_name") or "صنف", item.get("size_name") or "عادي",
                        int(item.get("quantity", 1)), float(item.get("unit_price", 0)),
                        json.dumps(extras_dict, ensure_ascii=False),
                    ),
                )
            conn.commit()
            order["local_order_id"] = local_order_id
            return was_new
        finally:
            conn.close()

    def _orders_for_sync(self, initial: bool) -> list[dict[str, Any]]:
        conn = database.get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            if initial:
                rows = conn.execute(
                    """
                    SELECT o.*, c.name AS customer_name, c.phone AS customer_phone,
                           c.address AS customer_address, d.name AS driver_name,
                           s.cashier_name AS cashier_name
                    FROM orders o
                    LEFT JOIN customers c ON c.id=o.customer_id
                    LEFT JOIN drivers d ON d.id=o.driver_id
                    LEFT JOIN shifts s ON s.id=o.shift_id
                    ORDER BY o.id
                    """
                ).fetchall()
            else:
                cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                rows = conn.execute(
                    """
                    SELECT o.*, c.name AS customer_name, c.phone AS customer_phone,
                           c.address AS customer_address, d.name AS driver_name,
                           s.cashier_name AS cashier_name
                    FROM orders o
                    LEFT JOIN customers c ON c.id=o.customer_id
                    LEFT JOIN drivers d ON d.id=o.driver_id
                    LEFT JOIN shifts s ON s.id=o.shift_id
                    WHERE o.status IN ('PENDING', 'DISPATCHED') OR o.closed_at>=?
                    ORDER BY o.id
                    """,
                    (cutoff,),
                ).fetchall()

            result: list[dict[str, Any]] = []
            for row in rows:
                source = row["source"] or "POS"
                online_status = row["online_status"]
                if source == "ONLINE" and online_status:
                    remote_status = online_status
                else:
                    remote_status = {
                        "PENDING": "PREPARING",
                        "DISPATCHED": "DISPATCHED",
                        "COMPLETED": "COMPLETED",
                        "CANCELLED": "CANCELLED",
                    }.get(row["status"], "NEW")
                fulfillment = "DELIVERY" if row["channel"] == "DELIVERY" else "PICKUP"
                payment_status = row["payment_status"]
                if not payment_status:
                    if row["payment_method"] == "CASH":
                        payment_status = "CASH_ON_DELIVERY" if fulfillment == "DELIVERY" else "CASH_ON_PICKUP"
                    else:
                        payment_status = "CONFIRMED"

                items = []
                for item in conn.execute(
                    """
                    SELECT oi.*, m.sync_id AS menu_item_sync_id
                    FROM order_items oi LEFT JOIN menu_items m ON m.id=oi.menu_item_id
                    WHERE oi.order_id=? ORDER BY oi.id
                    """,
                    (row["id"],),
                ):
                    try:
                        raw_extras = json.loads(item["extras_json"] or "{}")
                    except json.JSONDecodeError:
                        raw_extras = {}
                    if isinstance(raw_extras, dict):
                        extras = [
                            {"name": key, "price": value}
                            for key, value in raw_extras.items() if key != "__spicy__"
                        ]
                        if raw_extras.get("__spicy__"):
                            extras.append({"name": "حار", "price": 0, "system_key": "spicy"})
                    else:
                        extras = raw_extras
                    items.append({
                        "menu_item_sync_id": item["menu_item_sync_id"],
                        "item_name": item["item_name"] or "صنف",
                        "size_name": item["size_name"],
                        "quantity": item["quantity"],
                        "unit_price": item["price"],
                        "extras": extras,
                    })
                result.append({
                    "remote_id": row["remote_id"],
                    "local_order_id": row["id"],
                    "fulfillment": fulfillment,
                    "customer_name": row["customer_name"] or "عميل المطعم",
                    "customer_phone": row["customer_phone"] or "",
                    "area_name": row["area_name"] or "",
                    "detailed_address": strip_area_prefix(
                        row["customer_address"], row["area_name"]
                    ),
                    "payment_method": row["payment_method"],
                    "payment_status": payment_status,
                    "status": remote_status,
                    "subtotal": row["subtotal"],
                    "delivery_fee": row["delivery_fee"] or 0,
                    "discount": row["discount"] or 0,
                    "total": row["total"],
                    "notes": row["notes"] or "",
                    "cashier_name": row["cashier_name"] or config.ACTIVE_CASHIER_NAME,
                    "driver_name": row["driver_name"] or "",
                    "created_at": row["created_at"],
                    "closed_at": row["closed_at"],
                    "items": items,
                })
            return result
        finally:
            conn.close()

    def _push_pos_orders(self) -> None:
        initial = self._setting("web_initial_orders_synced", "0") != "1"
        orders = self._orders_for_sync(initial)
        for start in range(0, len(orders), 200):
            self._request_json(
                "/api/sync/pos-orders",
                method="POST",
                payload={"orders": orders[start:start + 200]},
            )
        if initial:
            self._set_setting("web_initial_orders_synced", "1")
