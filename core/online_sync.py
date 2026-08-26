# -*- coding: utf-8 -*-
"""Background synchronization between the local POS database and Broost web API."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

import certifi
from PyQt6.QtCore import QObject, pyqtSignal

import database
from core import config
from core.time_utils import to_local_db_timestamp
from core.order_finance import reconcile_order_finance


SYNC_REQUEST_TIMEOUT_SECONDS = 12
SYNC_REQUEST_ATTEMPTS = 2
SYNC_RETRY_DELAY_SECONDS = 0.65
POS_SYNC_BATCH_SIZE = 5
POS_SYNC_REQUEST_TIMEOUT_SECONDS = 25
MAX_SYNC_LOG_BYTES = 2 * 1024 * 1024
_SSL_CONTEXT: ssl.SSLContext | None = None
_SYNC_LOG_LOCK = threading.Lock()


def ssl_context() -> ssl.SSLContext:
    """Use the CA bundle shipped with the POS instead of machine-specific roots."""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    return _SSL_CONTEXT


def open_url(request: urllib.request.Request, timeout: int):
    kwargs: dict[str, Any] = {"timeout": timeout}
    if urllib.parse.urlparse(request.full_url).scheme.lower() == "https":
        kwargs["context"] = ssl_context()
    return urllib.request.urlopen(request, **kwargs)


def network_error_message(exc: BaseException) -> str:
    """Return an actionable Arabic message while keeping credentials out of logs/UI."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        reason = getattr(current, "reason", None)
        current = reason if isinstance(reason, BaseException) else current.__cause__

    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return "فشل التحقق من شهادة HTTPS. تأكد من تاريخ ووقت ويندوز ثم أعد المحاولة."
    if any(isinstance(item, (TimeoutError, socket.timeout)) for item in chain):
        return "انتهت مهلة الاتصال بالسيرفر. الاتصال بالإنترنت بطيء أو محجوب للبرنامج."
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "تعذر ترجمة اسم السيرفر (DNS) داخل البرنامج."
    text = " ".join(str(item).lower() for item in chain)
    if "proxy" in text or "407" in text:
        return "إعداد Proxy في ويندوز يمنع برنامج الكاشير من الوصول للسيرفر."
    if "refused" in text or "actively refused" in text:
        return "تم رفض اتصال البرنامج بالسيرفر بواسطة الشبكة أو الحماية."
    return f"تعذر الوصول إلى السيرفر: {chain[-1] if chain else exc}"


def log_network_error(operation: str, url: str, exc: BaseException) -> None:
    """Append a credential-free diagnostic line next to the local database."""
    parsed = urllib.parse.urlparse(url)
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | {operation} | "
        f"{safe_url} | {type(exc).__name__}: {network_error_message(exc)}\n"
    )
    path = os.path.join(database.BASE_DIR, "pos_sync.log")
    with _SYNC_LOG_LOCK:
        try:
            if os.path.exists(path) and os.path.getsize(path) >= MAX_SYNC_LOG_BYTES:
                previous = path + ".1"
                if os.path.exists(previous):
                    os.remove(previous)
                os.replace(path, previous)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass


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
    queued_action_completed = pyqtSignal(str, dict)
    queued_action_failed = pyqtSignal(str, dict, str)
    queue_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy_lock = threading.Lock()
        self._last_connected: bool | None = None
        self._last_connection_message = ""
        self._last_orders_push = 0.0
        self._last_cursor_probe = 0.0
        self._last_nonfatal_sync_error = ""
        self._consecutive_failures = 0
        self._last_success_at = 0.0

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

    @staticmethod
    def is_queueable_error(exc: BaseException) -> bool:
        """Only queue transient connectivity/server failures, never bad actions."""
        current: BaseException | None = exc
        seen: list[BaseException] = []
        while current is not None and current not in seen:
            seen.append(current)
            if isinstance(current, urllib.error.HTTPError):
                return current.code in (408, 425, 429, 500, 502, 503, 504)
            if isinstance(current, (urllib.error.URLError, OSError, TimeoutError, ssl.SSLError)):
                return True
            reason = getattr(current, "reason", None)
            current = reason if isinstance(reason, BaseException) else current.__cause__
        text = str(exc)
        return any(marker in text for marker in (
            "تعذر الوصول", "مهلة الاتصال", "DNS", "شهادة HTTPS",
            "Proxy", "تم رفض اتصال", "خطأ داخلي (HTTP 5",
        ))

    def queue_remote_action(
        self,
        action_type: str,
        remote_id: int,
        changes: dict[str, Any],
        context: dict[str, Any],
    ) -> int:
        action_key = f"order:{int(remote_id)}"
        safe_context = {
            key: value for key, value in context.items()
            if isinstance(value, (str, int, float, bool, type(None)))
        }
        conn = database.get_connection()
        try:
            conn.execute(
                "INSERT INTO pending_remote_actions "
                "(action_key, action_type, remote_id, changes_json, context_json) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(action_key) DO UPDATE SET "
                "action_type=excluded.action_type, changes_json=excluded.changes_json, "
                "context_json=excluded.context_json, created_at=CURRENT_TIMESTAMP, "
                "attempts=0, last_error=''",
                (
                    action_key, action_type, int(remote_id),
                    json.dumps(changes, ensure_ascii=False),
                    json.dumps(safe_context, ensure_ascii=False),
                ),
            )
            conn.commit()
            count = int(conn.execute(
                "SELECT COUNT(*) FROM pending_remote_actions"
            ).fetchone()[0])
        finally:
            conn.close()
        self.queue_changed.emit(count)
        return count

    def pending_remote_action_count(self) -> int:
        conn = database.get_connection()
        try:
            return int(conn.execute(
                "SELECT COUNT(*) FROM pending_remote_actions"
            ).fetchone()[0])
        finally:
            conn.close()

    def _flush_pending_remote_actions(self) -> int:
        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT action_key, action_type, remote_id, changes_json, context_json "
                "FROM pending_remote_actions ORDER BY created_at LIMIT 20"
            ).fetchall()
        finally:
            conn.close()

        for action_key, action_type, remote_id, changes_json, context_json in rows:
            try:
                changes = json.loads(changes_json or "{}")
                context = json.loads(context_json or "{}")
                self._request_json(
                    f"/api/sync/orders/{int(remote_id)}",
                    method="PATCH",
                    payload=changes,
                )
            except Exception as exc:
                if not self.is_queueable_error(exc):
                    conn = database.get_connection()
                    try:
                        conn.execute(
                            "DELETE FROM pending_remote_actions WHERE action_key=?",
                            (action_key,),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                    self.queued_action_failed.emit(
                        str(action_type), dict(context), str(exc)
                    )
                    continue
                conn = database.get_connection()
                try:
                    conn.execute(
                        "UPDATE pending_remote_actions SET attempts=attempts+1, last_error=? "
                        "WHERE action_key=?",
                        (str(exc)[:500], action_key),
                    )
                    conn.commit()
                finally:
                    conn.close()
                break

            conn = database.get_connection()
            try:
                conn.execute(
                    "DELETE FROM pending_remote_actions WHERE action_key=?",
                    (action_key,),
                )
                conn.commit()
            finally:
                conn.close()
            self.queued_action_completed.emit(str(action_type), dict(context))

        remaining = self.pending_remote_action_count()
        self.queue_changed.emit(remaining)
        return remaining

    def search_remote_customers(self, query: str = "") -> list[dict[str, Any]]:
        encoded = urllib.parse.quote((query or "").strip())
        return self._request_json(f"/api/sync/customers?query={encoded}")

    def get_remote_customer(self, phone: str) -> dict[str, Any]:
        encoded = urllib.parse.quote((phone or "").strip())
        return self._request_json(f"/api/sync/customers/{encoded}")

    def update_remote_customer(self, phone: str, **changes: Any) -> dict[str, Any]:
        encoded = urllib.parse.quote((phone or "").strip())
        return self._request_json(
            f"/api/sync/customers/{encoded}", method="PATCH", payload=changes
        )

    def delete_remote_customer_order(self, order_id: int) -> dict[str, Any]:
        return self._request_json(
            f"/api/sync/customer-orders/{int(order_id)}", method="DELETE"
        )

    def _poll_worker(self) -> None:
        if not self._busy_lock.acquire(blocking=False):
            return
        try:
            settings = self._settings()
            if settings.get("web_sync_enabled", "0") != "1":
                self._set_connected(False, "مزامنة الموقع متوقفة")
                return
            self._last_nonfatal_sync_error = ""
            pending_actions = self._flush_pending_remote_actions()
            self._sync_menu()
            self._pull_events()
            heartbeat_payload = self._cashier_day_context()
            # Confirm the cashier is online before the optional history mirror.
            # A slow first-time upload must never make the public site look shut.
            self._request_json(
                "/api/sync/heartbeat",
                method="POST",
                payload=heartbeat_payload,
            )
            if time.monotonic() - self._last_orders_push >= 20:
                try:
                    self._push_pos_orders()
                except Exception as exc:
                    # POS history is a secondary mirror. Never let one stale/bad
                    # historical row block incoming web orders or the heartbeat.
                    self._last_nonfatal_sync_error = str(exc)
                    log_network_error(
                        "pos-orders-push",
                        f"{self._connection_values()[0]}/api/sync/pos-orders",
                        exc,
                    )
                finally:
                    # Retry on the normal interval instead of hammering a sick
                    # backend on every UI poll.
                    self._last_orders_push = time.monotonic()
            # Refresh once more after the bounded POS batch so even the longest
            # allowed request remains inside the website's online window.
            self._request_json(
                "/api/sync/heartbeat",
                method="POST",
                payload=heartbeat_payload,
            )
            message = "متزامن أونلاين"
            if self._last_nonfatal_sync_error:
                message = "متصل ويستقبل الطلبات — إعادة محاولة رفع السجل تلقائيًا"
            elif pending_actions:
                message = f"متصل — {pending_actions} عملية تنتظر المزامنة"
            elif self._consecutive_failures:
                message = "عاد الاتصال وتمت المزامنة تلقائيًا"
            self._consecutive_failures = 0
            self._last_success_at = time.monotonic()
            self._set_connected(True, message)
        except Exception as exc:
            self._consecutive_failures += 1
            self._set_connected(
                False,
                f"أوفلاين — سيحاول النظام الرجوع تلقائيًا: {exc}",
            )
        finally:
            self._busy_lock.release()

    def _cashier_day_context(self) -> dict[str, Any]:
        """Send the exact business-day boundary used by the cashier reports."""
        payload: dict[str, Any] = {}
        try:
            business_start = database.get_business_day_start()
            payload["business_day_start"] = business_start.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            # A heartbeat must keep working even if the local reporting context
            # cannot be read temporarily.
            pass

        try:
            conn = database.get_connection()
            try:
                row = conn.execute(
                    "SELECT opened_at FROM shifts WHERE closed_at IS NULL "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            payload["shift_is_open"] = bool(row)
            if row and row[0]:
                payload["shift_opened_at"] = str(row[0])[:19]
        except Exception:
            pass
        return payload

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
        base_url = settings.get("web_server_url", "").strip().rstrip("/")
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
                with open_url(web_request, timeout=timeout) as response:
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
            except urllib.error.URLError as exc:
                log_network_error("connection-check", web_request.full_url, exc)
                return None, None, network_error_message(exc)
            except Exception as exc:
                log_network_error("connection-check", web_request.full_url, exc)
                return None, None, network_error_message(exc)

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
        *,
        timeout_seconds: int | None = None,
        attempts: int | None = None,
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
        request_timeout = timeout_seconds or SYNC_REQUEST_TIMEOUT_SECONDS
        request_attempts = attempts or SYNC_REQUEST_ATTEMPTS
        for attempt in range(request_attempts):
            try:
                with open_url(request, timeout=request_timeout) as response:
                    raw = response.read()
                    return json.loads(raw.decode("utf-8")) if raw else {}
            except urllib.error.HTTPError as exc:
                if exc.code in (500, 502, 503, 504) and attempt + 1 < request_attempts:
                    log_network_error("sync-json-retry", request.full_url, exc)
                    time.sleep(SYNC_RETRY_DELAY_SECONDS * (1.5 ** attempt))
                    continue
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
            except (urllib.error.URLError, OSError, TimeoutError, ssl.SSLError) as exc:
                log_network_error("sync-json", request.full_url, exc)
                if attempt + 1 < request_attempts:
                    time.sleep(SYNC_RETRY_DELAY_SECONDS * (1.5 ** attempt))
                    continue
                raise RuntimeError(network_error_message(exc)) from exc
        raise RuntimeError("تعذر إكمال طلب المزامنة")

    def _request_bytes(self, path: str) -> bytes:
        base_url, sync_key = self._connection_values()
        request = urllib.request.Request(
            f"{base_url}{path}",
            method="GET",
            headers={"X-Sync-Key": sync_key},
        )
        for attempt in range(SYNC_REQUEST_ATTEMPTS):
            try:
                with open_url(request, timeout=SYNC_REQUEST_TIMEOUT_SECONDS) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                log_network_error("sync-bytes", request.full_url, exc)
                if exc.code in (500, 502, 503, 504) and attempt + 1 < SYNC_REQUEST_ATTEMPTS:
                    time.sleep(SYNC_RETRY_DELAY_SECONDS)
                    continue
                raise RuntimeError(f"تعذر تنزيل الملف من السيرفر (HTTP {exc.code})") from exc
            except (urllib.error.URLError, OSError, TimeoutError, ssl.SSLError) as exc:
                log_network_error("sync-bytes", request.full_url, exc)
                if attempt + 1 < SYNC_REQUEST_ATTEMPTS:
                    time.sleep(SYNC_RETRY_DELAY_SECONDS)
                    continue
                raise RuntimeError(network_error_message(exc)) from exc
        raise RuntimeError("تعذر تنزيل الملف من السيرفر")

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
        local_epoch = self._setting("web_sync_epoch", "")
        result = self._request_json(f"/api/sync/events?after={last_event_id}")
        remote_epoch = str(result.get("sync_epoch") or "")
        server_last_event_id = result.get("server_last_event_id")
        cursor_reset = False

        # A client upgraded from the pre-epoch version has a valid event cursor
        # but no stored epoch. Adopt the server epoch without replaying the full
        # event history. Only a known, different epoch proves DB replacement.
        epoch_changed = bool(
            local_epoch and remote_epoch and remote_epoch != local_epoch
        )
        cursor_ahead = (
            server_last_event_id is not None
            and int(server_last_event_id or 0) < last_event_id
        )
        if epoch_changed or cursor_ahead:
            result = self._request_json("/api/sync/events?after=0")
            remote_epoch = str(result.get("sync_epoch") or remote_epoch)
            cursor_reset = True
        elif (
            not remote_epoch
            and last_event_id > 0
            and not result.get("events")
            and time.monotonic() - self._last_cursor_probe >= 300
        ):
            # Compatibility with an older backend that did not expose an epoch.
            # A restored/replaced database can restart event IDs from 1 while the
            # cashier still remembers a larger cursor from the previous database.
            self._last_cursor_probe = time.monotonic()
            probe = self._request_json("/api/sync/events?after=0")
            probe_last = int(
                probe.get("server_last_event_id", probe.get("last_event_id", 0)) or 0
            )
            if probe_last < last_event_id:
                result = probe
                remote_epoch = str(probe.get("sync_epoch") or "")
                cursor_reset = True

        if remote_epoch and remote_epoch != local_epoch:
            self._set_setting("web_sync_epoch", remote_epoch)

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
        elif cursor_reset:
            self._set_setting("web_last_event_id", int(result.get("last_event_id", 0) or 0))

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
            active_shift_id = config.ACTIVE_SHIFT_ID
            if active_shift_id and not cursor.execute(
                "SELECT 1 FROM shifts WHERE id=?", (active_shift_id,)
            ).fetchone():
                active_shift_id = None
            values = (
                customer_id, channel, payment_method, float(order.get("subtotal", 0)),
                float(order.get("delivery_fee", 0)), float(order.get("discount", 0)),
                float(order.get("total", 0)), cash_paid, 0.0, local_status,
                active_shift_id, order.get("notes") or "",
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
            reconcile_order_finance(
                conn, local_order_id, fallback_shift_id=active_shift_id
            )
            conn.commit()
            order["local_order_id"] = local_order_id
            return was_new
        finally:
            conn.close()

    def _orders_for_sync(
        self, initial: bool, limit: int | None = None
    ) -> list[dict[str, Any]]:
        conn = database.get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            if initial:
                rows = conn.execute(
                    """
                    SELECT o.*, q.queued_at AS sync_queue_token,
                           c.name AS customer_name, c.phone AS customer_phone,
                           c.address AS customer_address, d.name AS driver_name,
                           s.cashier_name AS cashier_name
                    FROM orders o
                    LEFT JOIN pos_order_sync_queue q ON q.local_order_id=o.id
                    LEFT JOIN customers c ON c.id=o.customer_id
                    LEFT JOIN drivers d ON d.id=o.driver_id
                    LEFT JOIN shifts s ON s.id=o.shift_id
                    ORDER BY o.id
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT o.*, q.queued_at AS sync_queue_token,
                           c.name AS customer_name, c.phone AS customer_phone,
                           c.address AS customer_address, d.name AS driver_name,
                           s.cashier_name AS cashier_name
                    FROM orders o
                    JOIN pos_order_sync_queue q ON q.local_order_id=o.id
                    LEFT JOIN customers c ON c.id=o.customer_id
                    LEFT JOIN drivers d ON d.id=o.driver_id
                    LEFT JOIN shifts s ON s.id=o.shift_id
                    ORDER BY q.queued_at DESC,
                             CASE WHEN o.source='ONLINE' THEN 0 ELSE 1 END,
                             o.id DESC
                    """
                ).fetchall()

            if limit is not None:
                rows = rows[:max(0, int(limit))]

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
                    "_sync_queue_token": row["sync_queue_token"],
                    "remote_id": row["remote_id"],
                    "local_order_id": row["id"],
                    "public_number": row["public_number"] or "",
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
        conn = database.get_connection()
        try:
            if initial:
                seeded = conn.execute(
                    "SELECT value FROM settings WHERE key='web_initial_orders_queued'"
                ).fetchone()
                if not seeded or seeded[0] != "1":
                    # Turn the first history upload into the same durable queue
                    # used by live edits. This lets us acknowledge a few rows
                    # per heartbeat without restarting from order number one.
                    conn.execute(
                        "INSERT OR IGNORE INTO pos_order_sync_queue "
                        "(local_order_id, queued_at) "
                        "SELECT id, CURRENT_TIMESTAMP FROM orders"
                    )
                    conn.execute(
                        "INSERT INTO settings (key, value) VALUES "
                        "('web_initial_orders_queued', '1') "
                        "ON CONFLICT(key) DO UPDATE SET value='1'"
                    )
                    conn.commit()
            deleted_local_order_ids = [
                int(row[0]) for row in conn.execute(
                    "SELECT local_order_id FROM pos_order_deletions "
                    "ORDER BY deleted_at, local_order_id LIMIT ?",
                    (POS_SYNC_BATCH_SIZE,),
                ).fetchall()
            ]
        finally:
            conn.close()

        remaining_slots = max(0, POS_SYNC_BATCH_SIZE - len(deleted_local_order_ids))
        orders = self._orders_for_sync(False, limit=remaining_slots)
        if orders or deleted_local_order_ids:
            wire_batch = [
                {key: value for key, value in order.items() if key != "_sync_queue_token"}
                for order in orders
            ]
            # A POS history push is deliberately attempted once. If the reply
            # is lost, the durable queue retries on a later poll; issuing a
            # second overlapping HTTP request is what used to exhaust Neon.
            result = self._request_json(
                "/api/sync/pos-orders",
                method="POST",
                payload={
                    "orders": wire_batch,
                    "deleted_local_order_ids": deleted_local_order_ids,
                },
                timeout_seconds=POS_SYNC_REQUEST_TIMEOUT_SECONDS,
                attempts=1,
            )
            mappings = result.get("mappings", {}) if isinstance(result, dict) else {}
            acknowledged_deletions = (
                result.get("deleted_local_order_ids", [])
                if isinstance(result, dict) else []
            )
            conn = database.get_connection()
            try:
                for local_order_id, remote_id in mappings.items():
                    conn.execute(
                        "UPDATE orders SET remote_id=NULL "
                        "WHERE source='ONLINE' AND remote_id=? AND id!=?",
                        (int(remote_id), int(local_order_id)),
                    )
                    conn.execute(
                        "UPDATE orders SET remote_id=? WHERE id=? AND source='ONLINE'",
                        (int(remote_id), int(local_order_id)),
                    )
                for local_order_id in acknowledged_deletions:
                    conn.execute(
                        "DELETE FROM pos_order_deletions WHERE local_order_id=?",
                        (int(local_order_id),),
                    )
                for sent_order in orders:
                    queue_token = sent_order.get("_sync_queue_token")
                    if queue_token:
                        conn.execute(
                            "DELETE FROM pos_order_sync_queue "
                            "WHERE local_order_id=? AND queued_at=?",
                            (int(sent_order["local_order_id"]), queue_token),
                        )
                conn.commit()
            finally:
                conn.close()

        if initial:
            conn = database.get_connection()
            try:
                pending = int(conn.execute(
                    "SELECT COUNT(*) FROM pos_order_sync_queue"
                ).fetchone()[0]) + int(conn.execute(
                    "SELECT COUNT(*) FROM pos_order_deletions"
                ).fetchone()[0])
            finally:
                conn.close()
            if pending == 0:
                self._set_setting("web_initial_orders_synced", "1")
