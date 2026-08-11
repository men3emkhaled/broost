# -*- coding: utf-8 -*-
"""FastAPI backend for the Broost customer site, admin dashboard and POS sync."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

if os.getenv("BROOST_LOAD_DOTENV", "1") != "0":
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

import httpx
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from webapp.db import (
    DatabaseError,
    DatabaseIntegrityError,
    USING_POSTGRES,
    connect_database,
    table_columns,
)
from webapp.phone_validation import valid_egyptian_mobile


if getattr(sys, "frozen", False):
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS"))
    BASE_DIR = RESOURCE_ROOT / "webapp"
    DEFAULT_DATA_DIR = Path(sys.executable).resolve().parent / "web_data"
else:
    RESOURCE_ROOT = Path(__file__).resolve().parent.parent
    BASE_DIR = Path(__file__).resolve().parent
    DEFAULT_DATA_DIR = BASE_DIR / "data"

STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.getenv("BROOST_WEB_DATA_DIR", str(DEFAULT_DATA_DIR)))
DB_PATH = DATA_DIR / "broost_web.db"
PROOFS_DIR = DATA_DIR / "payment_proofs"
MAX_PROOF_BYTES = 6 * 1024 * 1024
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "").strip()
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
LOYALTY_REWARD_POINTS = 100
LOYALTY_REWARD_MAX_SUBTOTAL = Decimal("150")
LOYALTY_REWARD_CODE_VALUE = Decimal("150")
POS_HEARTBEAT_TIMEOUT_SECONDS = 30

ORDER_STATUS_TRANSITIONS = {
    "NEW": {"PREPARING", "CANCELLED"},
    "PREPARING": {"READY", "DISPATCHED", "COMPLETED", "CANCELLED"},
    "READY": {"DISPATCHED", "COMPLETED", "CANCELLED"},
    # Returning an undelivered order to preparation is a deliberate driver-settlement path.
    "DISPATCHED": {"PREPARING", "COMPLETED", "CANCELLED"},
    "COMPLETED": {"CANCELLED"},
    "CANCELLED": set(),
}
WALLET_PAYMENT_TRANSITIONS = {
    "AWAITING_PAYMENT": set(),
    "PROOF_UPLOADED": {"CONFIRMED", "REJECTED"},
    "REJECTED": set(),
    "CONFIRMED": set(),
}


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_phone(value: str | None) -> str:
    """Use one comparable Egyptian phone shape without changing the saved display value."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("0020"):
        digits = digits[4:]
    elif digits.startswith("20") and len(digits) >= 12:
        digits = digits[2:]
    if digits and not digits.startswith("0"):
        digits = "0" + digits
    return digits


def strip_area_prefix(address: str | None, area_name: str | None) -> str:
    """Keep the village in its own field and remove repeated leading copies from details."""
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


@contextmanager
def db_connection(*, immediate: bool = False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect_database(DB_PATH)
    try:
        if immediate and not USING_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_web_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USING_POSTGRES:
        PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    with db_connection() as conn:
        schema_sql = """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS delivery_areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                delivery_fee REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                delivery_enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS categories (
                sync_id TEXT PRIMARY KEY,
                local_id INTEGER,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS menu_items (
                sync_id TEXT PRIMARY KEY,
                local_id INTEGER,
                category_sync_id TEXT NOT NULL,
                name TEXT NOT NULL,
                base_price REAL NOT NULL DEFAULT 0,
                is_available INTEGER NOT NULL DEFAULT 1,
                is_popular INTEGER NOT NULL DEFAULT 0,
                is_daily_offer INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(category_sync_id) REFERENCES categories(sync_id)
            );

            CREATE TABLE IF NOT EXISTS menu_item_sizes (
                sync_id TEXT PRIMARY KEY,
                local_id INTEGER,
                item_sync_id TEXT NOT NULL,
                name TEXT NOT NULL,
                price_offset REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(item_sync_id) REFERENCES menu_items(sync_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS menu_item_extras (
                sync_id TEXT PRIMARY KEY,
                local_id INTEGER,
                item_sync_id TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(item_sync_id) REFERENCES menu_items(sync_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS offers (
                sync_id TEXT PRIMARY KEY,
                local_id INTEGER,
                name TEXT NOT NULL,
                offer_price REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS offer_items (
                sync_id TEXT PRIMARY KEY,
                local_id INTEGER,
                offer_sync_id TEXT NOT NULL,
                item_sync_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(offer_sync_id) REFERENCES offers(sync_id) ON DELETE CASCADE,
                FOREIGN KEY(item_sync_id) REFERENCES menu_items(sync_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_number TEXT UNIQUE,
                resume_token TEXT UNIQUE,
                client_request_id TEXT UNIQUE,
                source TEXT NOT NULL DEFAULT 'ONLINE',
                local_order_id INTEGER,
                fulfillment TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                customer_phone_normalized TEXT,
                area_id INTEGER,
                area_name TEXT,
                detailed_address TEXT,
                payment_method TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                status TEXT NOT NULL,
                subtotal REAL NOT NULL,
                delivery_fee REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL,
                notes TEXT,
                proof_filename TEXT,
                proof_original_name TEXT,
                proof_mime_type TEXT,
                transfer_phone_suffix TEXT,
                cashier_name TEXT,
                driver_name TEXT,
                reward_code TEXT,
                loyalty_points_earned INTEGER NOT NULL DEFAULT 0,
                loyalty_points_redeemed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                cancelled_by TEXT,
                FOREIGN KEY(area_id) REFERENCES delivery_areas(id),
                UNIQUE(source, local_order_id)
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_sync_id TEXT,
                item_name TEXT NOT NULL,
                size_name TEXT,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                extras_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS customer_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_normalized TEXT NOT NULL,
                order_id INTEGER,
                issue_type TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                is_resolved INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT 'ADMIN',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                review_text TEXT NOT NULL,
                rating INTEGER NOT NULL DEFAULT 5,
                is_visible INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS loyalty_accounts (
                phone_normalized TEXT PRIMARY KEY,
                points_balance INTEGER NOT NULL DEFAULT 0,
                lifetime_points INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reward_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                phone_normalized TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 150,
                points_cost INTEGER NOT NULL DEFAULT 100,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                reserved_order_id INTEGER,
                used_order_id INTEGER,
                created_at TEXT NOT NULL,
                reserved_at TEXT,
                used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS loyalty_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_normalized TEXT NOT NULL,
                order_id INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                points INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
                UNIQUE(order_id, transaction_type)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_order_events_id ON order_events(id);
            CREATE INDEX IF NOT EXISTS idx_customer_issues_phone ON customer_issues(phone_normalized, is_resolved);
            CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_phone ON loyalty_transactions(phone_normalized, created_at);
            CREATE INDEX IF NOT EXISTS idx_reward_codes_phone ON reward_codes(phone_normalized, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_offer_items_offer ON offer_items(offer_sync_id);
            """
        if USING_POSTGRES:
            schema_sql = schema_sql.replace(
                "id INTEGER PRIMARY KEY AUTOINCREMENT", "id BIGSERIAL PRIMARY KEY"
            )
            schema_sql = re.sub(r"\b(order_id|area_id) INTEGER\b", r"\1 BIGINT", schema_sql)
        conn.executescript(schema_sql)

        order_columns = table_columns(conn, "orders")
        if "customer_phone_normalized" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN customer_phone_normalized TEXT")
        if "loyalty_points_earned" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN loyalty_points_earned INTEGER NOT NULL DEFAULT 0")
        if "loyalty_points_redeemed" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN loyalty_points_redeemed INTEGER NOT NULL DEFAULT 0")
        if "cancelled_by" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN cancelled_by TEXT")
        if "proof_url" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN proof_url TEXT")
        if "proof_delete_url" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN proof_delete_url TEXT")
        if "proof_storage_id" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN proof_storage_id TEXT")
        if "reward_code" not in order_columns:
            conn.execute("ALTER TABLE orders ADD COLUMN reward_code TEXT")
        area_columns = table_columns(conn, "delivery_areas")
        if "delivery_enabled" not in area_columns:
            conn.execute(
                "ALTER TABLE delivery_areas ADD COLUMN delivery_enabled INTEGER NOT NULL DEFAULT 1"
            )
        menu_item_columns = table_columns(conn, "menu_items")
        if "is_daily_offer" not in menu_item_columns:
            conn.execute("ALTER TABLE menu_items ADD COLUMN is_daily_offer INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_customer_phone "
            "ON orders(customer_phone_normalized)"
        )

        for row in conn.execute(
            "SELECT id, customer_phone FROM orders "
            "WHERE customer_phone_normalized IS NULL OR customer_phone_normalized=''"
        ).fetchall():
            conn.execute(
                "UPDATE orders SET customer_phone_normalized=? WHERE id=?",
                (normalize_phone(row["customer_phone"]), row["id"]),
            )

        # ACCEPTED used to be a separate customer-visible stage. It is now the
        # same stage as confirmed/preparing, including existing open orders.
        conn.execute("UPDATE orders SET status='PREPARING' WHERE status='ACCEPTED'")

        # Older POS sync versions stripped the UTC marker before pushing online
        # orders back. Restore the canonical UTC representation once.
        timestamp_fix = conn.execute(
            "SELECT 1 FROM settings WHERE key='online_timestamp_timezone_fixed_v1'"
        ).fetchone()
        if not timestamp_fix:
            conn.execute(
                "UPDATE orders SET created_at=replace(created_at, ' ', 'T') || 'Z' "
                "WHERE source='ONLINE' AND created_at IS NOT NULL "
                "AND created_at NOT LIKE '%Z' AND created_at NOT LIKE '%+__:__'"
            )
            conn.execute(
                "UPDATE orders SET closed_at=replace(closed_at, ' ', 'T') || 'Z' "
                "WHERE source='ONLINE' AND closed_at IS NOT NULL "
                "AND closed_at NOT LIKE '%Z' AND closed_at NOT LIKE '%+__:__'"
            )
            set_setting(conn, "online_timestamp_timezone_fixed_v1", "1")

        defaults = {
            "restaurant_name": "Broost",
            "wallet_number": "",
            "ordering_enabled": "1",
            "business_hours": "",
            "branch_address": "",
            "contact_phone": "",
            "whatsapp_number": "",
            "map_url": "",
            "facebook_url": "",
            "admin_password": os.getenv("BROOST_ADMIN_PASSWORD", "9999"),
            "sync_key": os.getenv("BROOST_SYNC_KEY", "broost-local-sync"),
            "sync_epoch": secrets.token_hex(16),
            "menu_version": "0",
            "menu_updated_at": utc_now(),
        }
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO NOTHING",
            defaults.items(),
        )
        # In hosted deployments the environment is the source of truth for
        # secrets, including after a database import or secret rotation.
        if os.getenv("BROOST_ADMIN_PASSWORD"):
            set_setting(conn, "admin_password", os.environ["BROOST_ADMIN_PASSWORD"])
        if os.getenv("BROOST_SYNC_KEY"):
            set_setting(conn, "sync_key", os.environ["BROOST_SYNC_KEY"])

        # Repair any interrupted historical loyalty reconciliation on startup.
        # Ledger uniqueness makes this safe to run repeatedly without duplicating points.
        loyalty_order_ids = conn.execute(
            "SELECT id FROM orders WHERE source='ONLINE' AND ("
            "status IN ('COMPLETED', 'CANCELLED') OR loyalty_points_earned>0 "
            "OR loyalty_points_redeemed>0 OR EXISTS ("
            "SELECT 1 FROM loyalty_transactions lt WHERE lt.order_id=orders.id))"
        ).fetchall()
        for loyalty_order in loyalty_order_ids:
            reconcile_order_loyalty(conn, loyalty_order["id"])


def setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def bump_menu_version(conn: sqlite3.Connection) -> int:
    version = int(setting(conn, "menu_version", "0")) + 1
    set_setting(conn, "menu_version", version)
    set_setting(conn, "menu_updated_at", utc_now())
    return version


def loyalty_points_for_paid_amount(amount: Any) -> int:
    """One point per paid 10 EGP: 170 EGP earns exactly 17 points."""
    paid = max(Decimal("0"), Decimal(str(amount or 0)))
    return int((paid / Decimal("10")).to_integral_value(rounding=ROUND_FLOOR))


def loyalty_profile(conn: sqlite3.Connection, phone: str | None) -> dict[str, Any]:
    normalized = normalize_phone(phone)
    row = conn.execute(
        "SELECT points_balance, lifetime_points FROM loyalty_accounts WHERE phone_normalized=?",
        (normalized,),
    ).fetchone() if normalized else None
    balance = int(row["points_balance"] or 0) if row else 0
    lifetime = int(row["lifetime_points"] or 0) if row else 0
    reward_codes = [dict(code) for code in conn.execute(
        "SELECT code, value, points_cost, created_at FROM reward_codes "
        "WHERE phone_normalized=? AND status='ACTIVE' ORDER BY id DESC",
        (normalized,),
    ).fetchall()] if normalized else []
    return {
        "points": balance,
        "lifetime_points": lifetime,
        "reward_available": balance >= LOYALTY_REWARD_POINTS,
        "points_to_reward": max(0, LOYALTY_REWARD_POINTS - balance),
        "reward_cost": LOYALTY_REWARD_POINTS,
        "reward_max_subtotal": float(LOYALTY_REWARD_MAX_SUBTOTAL),
        "reward_code_value": float(LOYALTY_REWARD_CODE_VALUE),
        "reward_codes": reward_codes,
    }


def cashier_is_online(conn: sqlite3.Connection) -> bool:
    """Treat the hosted restaurant as open only while the desktop is checking in."""
    if APP_ENV != "production":
        return True
    last_seen = setting(conn, "pos_last_seen_at", "")
    if not last_seen:
        return False
    try:
        seen_at = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - seen_at).total_seconds() <= POS_HEARTBEAT_TIMEOUT_SECONDS


def ordering_is_available(conn: sqlite3.Connection) -> bool:
    return setting(conn, "ordering_enabled", "1") == "1" and cashier_is_online(conn)


def adjust_loyalty_account(
    conn: sqlite3.Connection,
    phone_normalized: str,
    points_delta: int,
    *,
    lifetime_delta: int = 0,
) -> None:
    now = utc_now()
    conn.execute(
        "INSERT INTO loyalty_accounts "
        "(phone_normalized, points_balance, lifetime_points, updated_at) VALUES (?, 0, 0, ?) "
        "ON CONFLICT(phone_normalized) DO NOTHING",
        (phone_normalized, now),
    )
    conn.execute(
        "UPDATE loyalty_accounts SET points_balance=points_balance+?, "
        "lifetime_points=lifetime_points+?, updated_at=? WHERE phone_normalized=?",
        (points_delta, lifetime_delta, now, phone_normalized),
    )


def loyalty_transaction_exists(
    conn: sqlite3.Connection, order_id: int, transaction_type: str
) -> bool:
    return conn.execute(
        "SELECT 1 FROM loyalty_transactions WHERE order_id=? AND transaction_type=?",
        (order_id, transaction_type),
    ).fetchone() is not None


def record_loyalty_transaction(
    conn: sqlite3.Connection,
    phone_normalized: str,
    order_id: int,
    transaction_type: str,
    points: int,
) -> None:
    conn.execute(
        "INSERT INTO loyalty_transactions "
        "(phone_normalized, order_id, transaction_type, points, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (phone_normalized, order_id, transaction_type, points, utc_now()),
    )


def reconcile_order_loyalty(conn: sqlite3.Connection, order_id: int) -> None:
    """Award or return points exactly once as an online order changes state."""
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order or order["source"] != "ONLINE":
        return
    phone = order["customer_phone_normalized"] or normalize_phone(order["customer_phone"])
    if not phone:
        return

    reward_code = str(order["reward_code"] or "").strip()
    if reward_code:
        if order["status"] == "CANCELLED":
            conn.execute(
                "UPDATE reward_codes SET status='ACTIVE', reserved_order_id=NULL, reserved_at=NULL "
                "WHERE code=? AND status='RESERVED' AND reserved_order_id=?",
                (reward_code, order_id),
            )
        elif order["status"] == "COMPLETED":
            conn.execute(
                "UPDATE reward_codes SET status='USED', used_order_id=?, used_at=? "
                "WHERE code=? AND status='RESERVED' AND reserved_order_id=?",
                (order_id, utc_now(), reward_code, order_id),
            )

    paid = order["payment_method"] == "CASH" or order["payment_status"] == "CONFIRMED"
    should_earn = order["status"] == "COMPLETED" and paid
    earned_before = loyalty_transaction_exists(conn, order_id, "EARN")
    reversed_before = loyalty_transaction_exists(conn, order_id, "EARN_REVERSAL")

    if should_earn and not earned_before:
        points = loyalty_points_for_paid_amount(order["total"])
        if points:
            adjust_loyalty_account(conn, phone, points, lifetime_delta=points)
            record_loyalty_transaction(conn, phone, order_id, "EARN", points)
            conn.execute(
                "UPDATE orders SET loyalty_points_earned=? WHERE id=?", (points, order_id)
            )
    elif not should_earn and earned_before and not reversed_before:
        earned_row = conn.execute(
            "SELECT points FROM loyalty_transactions WHERE order_id=? AND transaction_type='EARN'",
            (order_id,),
        ).fetchone()
        points = int(earned_row["points"] or 0) if earned_row else 0
        if points:
            adjust_loyalty_account(conn, phone, -points, lifetime_delta=-points)
            record_loyalty_transaction(conn, phone, order_id, "EARN_REVERSAL", -points)
            conn.execute("UPDATE orders SET loyalty_points_earned=0 WHERE id=?", (order_id,))

    redeem_row = conn.execute(
        "SELECT points FROM loyalty_transactions "
        "WHERE order_id=? AND transaction_type='REDEEM'",
        (order_id,),
    ).fetchone()
    if (
        order["status"] == "CANCELLED"
        and redeem_row
        and not loyalty_transaction_exists(conn, order_id, "REDEEM_REFUND")
    ):
        refunded = abs(int(redeem_row["points"] or 0))
        if not refunded:
            return
        adjust_loyalty_account(conn, phone, refunded)
        record_loyalty_transaction(conn, phone, order_id, "REDEEM_REFUND", refunded)
        conn.execute(
            "UPDATE orders SET loyalty_points_redeemed=? WHERE id=?", (refunded, order_id)
        )


def validate_order_changes(order: sqlite3.Row, changes: dict[str, Any]) -> None:
    """Enforce the one canonical order/payment state machine for every writer."""
    current_status = "PREPARING" if order["status"] == "ACCEPTED" else order["status"]
    requested_status = changes.get("status")
    if requested_status == "ACCEPTED":
        requested_status = "PREPARING"
        changes["status"] = requested_status

    current_payment = order["payment_status"]
    requested_payment = changes.get("payment_status")
    if (
        current_status in ("COMPLETED", "CANCELLED")
        and requested_payment
        and requested_payment != current_payment
    ):
        raise HTTPException(status_code=409, detail="حالة الدفع لا تتغير بعد إغلاق الطلب")
    if requested_payment and requested_payment != current_payment:
        if order["payment_method"] != "WALLET":
            raise HTTPException(status_code=409, detail="حالة دفع الطلب النقدي لا يمكن تغييرها")
        allowed_payments = WALLET_PAYMENT_TRANSITIONS.get(current_payment, set())
        if requested_payment not in allowed_payments:
            raise HTTPException(
                status_code=409,
                detail="تغيير حالة المحفظة غير مسموح من الحالة الحالية",
            )

    if not requested_status or requested_status == current_status:
        return
    if requested_status not in ORDER_STATUS_TRANSITIONS.get(current_status, set()):
        if current_status == "CANCELLED":
            detail = "الطلب الملغي لا يمكن إعادته للعمل مرة أخرى"
        elif current_status == "COMPLETED":
            detail = "الطلب المكتمل لا يمكن إرجاعه لحالة جارية"
        else:
            detail = f"لا يمكن نقل الطلب من {current_status} إلى {requested_status}"
        raise HTTPException(status_code=409, detail=detail)

    fulfillment = order["fulfillment"]
    if fulfillment == "DELIVERY" and requested_status == "READY":
        raise HTTPException(
            status_code=409,
            detail="طلب الدليفري يصبح جاهزًا ويخرج للتوصيل عند تكليف الطيار من السيستم",
        )
    if fulfillment == "PICKUP" and requested_status == "DISPATCHED":
        raise HTTPException(status_code=409, detail="طلب الاستلام من المطعم لا يخرج مع طيار")
    if fulfillment == "DELIVERY" and requested_status == "DISPATCHED":
        driver_name = str(changes.get("driver_name") or order["driver_name"] or "").strip()
        if not driver_name:
            raise HTTPException(status_code=409, detail="اختيار الطيار إجباري قبل خروج الطلب")
    if (
        fulfillment == "DELIVERY"
        and requested_status == "COMPLETED"
        and current_status != "DISPATCHED"
    ):
        raise HTTPException(status_code=409, detail="طلب الدليفري لا يكتمل قبل تكليف الطيار")

    effective_payment = requested_payment or current_payment
    if (
        order["payment_method"] == "WALLET"
        and requested_status in ("PREPARING", "READY", "DISPATCHED", "COMPLETED")
        and effective_payment != "CONFIRMED"
    ):
        raise HTTPException(
            status_code=409,
            detail="لا يمكن تجهيز طلب المحفظة قبل تأكيد صورة التحويل",
        )


def emit_event(
    conn: sqlite3.Connection,
    order_id: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO order_events (order_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
        (order_id, event_type, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
    )


def require_admin(x_admin_key: str = Header(default="")) -> None:
    with db_connection() as conn:
        expected = setting(conn, "admin_password", "9999")
    if not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="بيانات دخول لوحة الأدمن غير صحيحة")


def require_sync(x_sync_key: str = Header(default="")) -> None:
    with db_connection() as conn:
        expected = setting(conn, "sync_key", "broost-local-sync")
        if not secrets.compare_digest(x_sync_key, expected):
            raise HTTPException(status_code=401, detail="مفتاح مزامنة برنامج الكاشير غير صحيح")
        set_setting(conn, "pos_last_seen_at", utc_now())


class OrderItemInput(BaseModel):
    item_id: str | None = None
    offer_id: str | None = None
    quantity: int = Field(ge=1, le=30)
    size_id: str | None = None
    extra_ids: list[str] = Field(default_factory=list, max_length=30)
    spicy: bool = False


class CreateOrderInput(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=120)
    fulfillment: Literal["DELIVERY", "PICKUP"]
    payment_method: Literal["CASH", "WALLET"]
    customer_name: str = Field(min_length=2, max_length=120)
    customer_phone: str = Field(min_length=7, max_length=30)
    area_id: int | None = None
    detailed_address: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=500)
    items: list[OrderItemInput] = Field(min_length=1, max_length=80)
    redeem_reward: bool = False
    reward_code: str = Field(default="", max_length=40)


class RewardCodeInput(BaseModel):
    phone: str = Field(min_length=7, max_length=30)


class ProofInput(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    data_base64: str
    transfer_phone_suffix: str = Field(default="", max_length=8)


class AreaInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    delivery_fee: float = Field(ge=0, le=100000)
    is_active: bool = True
    delivery_enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)


class AreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    delivery_fee: float | None = Field(default=None, ge=0, le=100000)
    is_active: bool | None = None
    delivery_enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class SettingsInput(BaseModel):
    restaurant_name: str = Field(min_length=1, max_length=120)
    wallet_number: str = Field(default="", max_length=60)
    ordering_enabled: bool
    business_hours: str = Field(default="", max_length=240)
    branch_address: str = Field(default="", max_length=500)
    contact_phone: str = Field(default="", max_length=60)
    whatsapp_number: str = Field(default="", max_length=60)
    map_url: str = Field(default="", max_length=500)
    facebook_url: str = Field(default="", max_length=500)


class ReviewInput(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    review_text: str = Field(min_length=4, max_length=600)
    rating: int = Field(default=5, ge=1, le=5)
    is_visible: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)


class CustomerIssueInput(BaseModel):
    issue_type: Literal[
        "NO_SHOW", "WRONG_ADDRESS", "UNREACHABLE", "INVALID_WALLET_PROOF", "OTHER"
    ]
    note: str = Field(default="", max_length=500)


class CustomerIssueUpdate(BaseModel):
    is_resolved: bool


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=10000)
    is_active: bool = True


class MenuOptionInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(ge=-100000, le=100000)


class MenuItemAdminInput(BaseModel):
    category_sync_id: str
    name: str = Field(min_length=1, max_length=160)
    base_price: float = Field(ge=0, le=100000)
    is_available: bool = True
    is_popular: bool = False
    is_daily_offer: bool = False
    sizes: list[MenuOptionInput] = Field(default_factory=list)
    extras: list[MenuOptionInput] = Field(default_factory=list)


class OfferComponentInput(BaseModel):
    item_sync_id: str
    quantity: int = Field(ge=1, le=30)


class OfferAdminInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    offer_price: float = Field(ge=0, le=100000)
    is_active: bool = True
    items: list[OfferComponentInput] = Field(min_length=1, max_length=30)


class OrderAdminUpdate(BaseModel):
    status: Literal[
        "NEW", "ACCEPTED", "PREPARING", "READY", "DISPATCHED", "COMPLETED", "CANCELLED"
    ] | None = None
    payment_status: Literal[
        "CASH_ON_DELIVERY", "CASH_ON_PICKUP", "AWAITING_PAYMENT", "PROOF_UPLOADED", "CONFIRMED", "REJECTED"
    ] | None = None
    cashier_name: str | None = Field(default=None, max_length=120)
    driver_name: str | None = Field(default=None, max_length=120)


class SyncMenuInput(BaseModel):
    known_server_version: int = 0
    categories: list[dict[str, Any]]
    items: list[dict[str, Any]]
    sizes: list[dict[str, Any]] = Field(default_factory=list)
    extras: list[dict[str, Any]] = Field(default_factory=list)
    offers: list[dict[str, Any]] = Field(default_factory=list)
    offer_items: list[dict[str, Any]] = Field(default_factory=list)


class PosOrdersInput(BaseModel):
    orders: list[dict[str, Any]] = Field(max_length=250)


def read_menu(conn: sqlite3.Connection, include_deleted: bool = False) -> dict[str, Any]:
    deleted_filter = "" if include_deleted else "WHERE is_deleted=0"
    categories = [dict(row) for row in conn.execute(
        f"SELECT * FROM categories {deleted_filter} ORDER BY sort_order, name"
    )]
    item_filter = "" if include_deleted else "WHERE is_deleted=0"
    items = [dict(row) for row in conn.execute(
        f"SELECT * FROM menu_items {item_filter} ORDER BY name"
    )]
    sizes = [dict(row) for row in conn.execute(
        "SELECT * FROM menu_item_sizes ORDER BY local_id, name"
    )]
    extras = [dict(row) for row in conn.execute(
        "SELECT * FROM menu_item_extras ORDER BY local_id, name"
    )]
    offer_filter = "" if include_deleted else "WHERE is_deleted=0"
    offers = [dict(row) for row in conn.execute(
        f"SELECT * FROM offers {offer_filter} ORDER BY local_id, name"
    )]
    offer_items = [dict(row) for row in conn.execute(
        "SELECT * FROM offer_items ORDER BY local_id, sync_id"
    )]
    return {
        "version": int(setting(conn, "menu_version", "0")),
        "updated_at": setting(conn, "menu_updated_at", ""),
        "categories": categories,
        "items": items,
        "sizes": sizes,
        "extras": extras,
        "offers": offers,
        "offer_items": offer_items,
    }


def customer_issue_rows(conn: sqlite3.Connection, phone: str | None) -> list[dict[str, Any]]:
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM customer_issues WHERE phone_normalized=? "
            "ORDER BY is_resolved, created_at DESC",
            (normalized,),
        ).fetchall()
    ]


def customer_reliability(conn: sqlite3.Connection, phone: str | None) -> dict[str, Any]:
    normalized = normalize_phone(phone)
    if not normalized:
        return {
            "status": "UNKNOWN",
            "label": "بدون رقم",
            "completed_orders": 0,
            "cancelled_orders": 0,
            "total_orders": 0,
            "open_issues": 0,
            "recorded_issues": 0,
            "confirmed_wallets": 0,
            "last_order_at": None,
            "last_terminal_status": None,
            "order_mood": "NEUTRAL",
            "needs_call": False,
        }

    stats = conn.execute(
        """
        SELECT
            COUNT(*) AS total_orders,
            COALESCE(SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END), 0) AS completed_orders,
            COALESCE(SUM(CASE WHEN status='CANCELLED' THEN 1 ELSE 0 END), 0) AS cancelled_orders,
            COALESCE(SUM(CASE WHEN payment_method='WALLET' AND payment_status='CONFIRMED'
                              AND status!='CANCELLED' THEN 1 ELSE 0 END), 0) AS confirmed_wallets,
            MAX(created_at) AS last_order_at
        FROM orders
        WHERE customer_phone_normalized=?
        """,
        (normalized,),
    ).fetchone()
    issues = conn.execute(
        """
        SELECT COUNT(*) AS recorded_issues,
               COALESCE(SUM(CASE WHEN is_resolved=0 THEN 1 ELSE 0 END), 0) AS open_issues
        FROM customer_issues WHERE phone_normalized=?
        """,
        (normalized,),
    ).fetchone()
    latest_terminal = conn.execute(
        """
        SELECT status FROM orders
        WHERE customer_phone_normalized=? AND status IN ('COMPLETED', 'CANCELLED')
        ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    completed = int(stats["completed_orders"] or 0)
    cancelled = int(stats["cancelled_orders"] or 0)
    open_issues = int(issues["open_issues"] or 0)
    last_terminal_status = latest_terminal["status"] if latest_terminal else None
    if completed >= 1:
        order_mood = "HAPPY"
    elif open_issues or last_terminal_status == "CANCELLED":
        order_mood = "ANGRY"
    else:
        order_mood = "NEUTRAL"
    if completed >= 1:
        status, label = "RELIABLE", "موثوق"
    elif open_issues or last_terminal_status == "CANCELLED":
        status, label = "NEEDS_CONFIRMATION", "يحتاج تأكيد"
    else:
        status, label = "NEW", "عميل جديد"
    return {
        "status": status,
        "label": label,
        "completed_orders": completed,
        "cancelled_orders": cancelled,
        "total_orders": int(stats["total_orders"] or 0),
        "open_issues": open_issues,
        "recorded_issues": int(issues["recorded_issues"] or 0),
        "confirmed_wallets": int(stats["confirmed_wallets"] or 0),
        "last_order_at": stats["last_order_at"],
        "last_terminal_status": last_terminal_status,
        "order_mood": order_mood,
        "needs_call": status == "NEEDS_CONFIRMATION",
    }


def order_to_dict(conn: sqlite3.Connection, order_row: sqlite3.Row) -> dict[str, Any]:
    data = dict(order_row)
    data["items"] = [
        {
            **dict(row),
            "extras": json.loads(row["extras_json"] or "[]"),
        }
        for row in conn.execute(
            "SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order_row["id"],)
        )
    ]
    data["has_payment_proof"] = bool(data.get("proof_filename"))
    data["customer_reliability"] = customer_reliability(conn, data.get("customer_phone"))
    profile = loyalty_profile(conn, data.get("customer_phone"))
    profile.update({
        "points_earned": int(data.get("loyalty_points_earned") or 0),
        "points_redeemed": int(data.get("loyalty_points_redeemed") or 0),
        "pending_points": (
            loyalty_points_for_paid_amount(data.get("total", 0))
            if data.get("status") not in ("COMPLETED", "CANCELLED")
            else 0
        ),
    })
    data["loyalty"] = profile
    reward_code = str(data.get("reward_code") or "").strip()
    if reward_code:
        reward = conn.execute(
            "SELECT code, value, status FROM reward_codes WHERE code=?",
            (reward_code,),
        ).fetchone()
        data["reward"] = dict(reward) if reward else {
            "code": reward_code,
            "value": float(data.get("discount") or 0),
            "status": "UNKNOWN",
        }
    else:
        data["reward"] = None
    data.pop("proof_filename", None)
    data.pop("proof_url", None)
    data.pop("proof_delete_url", None)
    data.pop("proof_storage_id", None)
    return data


def public_order_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    data = order_to_dict(conn, row)
    data["detailed_address"] = strip_area_prefix(
        data.get("detailed_address"), data.get("area_name")
    )
    for key in (
        "id", "client_request_id", "source", "local_order_id", "proof_original_name",
        "proof_mime_type", "cashier_name", "driver_name", "customer_phone_normalized",
        "customer_reliability",
    ):
        data.pop(key, None)
    return data


def validate_production_config() -> None:
    if APP_ENV != "production":
        return
    missing: list[str] = []
    if not USING_POSTGRES:
        missing.append("DATABASE_URL")
    if not CLOUDINARY_URL:
        missing.append("CLOUDINARY_URL")
    if os.getenv("BROOST_ADMIN_PASSWORD", "9999") == "9999":
        missing.append("BROOST_ADMIN_PASSWORD")
    if os.getenv("BROOST_SYNC_KEY", "broost-local-sync") == "broost-local-sync":
        missing.append("BROOST_SYNC_KEY")
    if missing:
        raise RuntimeError(
            "Missing secure production environment variables: " + ", ".join(missing)
        )


validate_production_config()
init_web_db()
app = FastAPI(title="Broost Ordering API", version="1.0.0")
cors_value = os.getenv("CORS_ORIGINS", "*").strip()
cors_origins = [item.strip() for item in cors_value.split(",") if item.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key", "X-Sync-Key"],
)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/", include_in_schema=False)
def customer_site() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_site() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/logo.ico", include_in_schema=False)
def brand_icon() -> FileResponse:
    return FileResponse(RESOURCE_ROOT / "logo.ico", media_type="image/x-icon")


@app.get("/health")
def health() -> dict[str, str]:
    with db_connection() as conn:
        conn.execute("SELECT 1 AS ok").fetchone()
    return {
        "status": "ok",
        "time": utc_now(),
        "database": "postgresql" if USING_POSTGRES else "sqlite",
        "proof_storage": "cloudinary" if CLOUDINARY_URL else "local",
    }


@app.get("/api/store")
def store_snapshot() -> dict[str, Any]:
    with db_connection() as conn:
        areas = [dict(row) for row in conn.execute(
            "SELECT id, name, delivery_fee, delivery_enabled, sort_order FROM delivery_areas "
            "WHERE is_active=1 ORDER BY sort_order, name"
        )]
        menu = read_menu(conn)
        available_category_ids = {c["sync_id"] for c in menu["categories"] if c["is_active"]}
        menu["categories"] = [c for c in menu["categories"] if c["is_active"]]
        menu["items"] = [
            item for item in menu["items"]
            if item["is_available"] and item["category_sync_id"] in available_category_ids
        ]
        available_item_ids = {item["sync_id"] for item in menu["items"]}
        offer_components: dict[str, list[dict[str, Any]]] = {}
        for component in menu["offer_items"]:
            offer_components.setdefault(component["offer_sync_id"], []).append(component)
        menu["offers"] = [
            offer for offer in menu["offers"]
            if offer["is_active"]
            and offer_components.get(offer["sync_id"])
            and all(
                part["item_sync_id"] in available_item_ids
                for part in offer_components[offer["sync_id"]]
            )
        ]
        visible_offer_ids = {offer["sync_id"] for offer in menu["offers"]}
        menu["offer_items"] = [
            part for part in menu["offer_items"]
            if part["offer_sync_id"] in visible_offer_ids
        ]
        reviews = [dict(row) for row in conn.execute(
            "SELECT id, customer_name, review_text, rating FROM reviews "
            "WHERE is_visible=1 ORDER BY sort_order, id DESC"
        ).fetchall()]
        cashier_online = cashier_is_online(conn)
        return {
            "restaurant_name": setting(conn, "restaurant_name", "Broost"),
            "wallet_available": bool(setting(conn, "wallet_number", "").strip()),
            "ordering_enabled": ordering_is_available(conn),
            "cashier_online": cashier_online,
            "business_hours": setting(conn, "business_hours", ""),
            "branch_address": setting(conn, "branch_address", ""),
            "contact_phone": setting(conn, "contact_phone", ""),
            "whatsapp_number": setting(conn, "whatsapp_number", ""),
            "map_url": setting(conn, "map_url", ""),
            "facebook_url": setting(conn, "facebook_url", ""),
            "areas": areas,
            "reviews": reviews,
            "menu": menu,
        }


@app.get("/api/loyalty")
def public_loyalty(phone: str = Query(min_length=7, max_length=30)) -> dict[str, Any]:
    if not valid_egyptian_mobile(phone):
        raise HTTPException(
            status_code=422,
            detail="رقم الموبايل لازم يكون 11 رقم ويبدأ بـ010 أو 011 أو 012 أو 015",
        )
    normalized = phone.strip()
    with db_connection() as conn:
        result = loyalty_profile(conn, normalized)
        identity = conn.execute(
            "SELECT customer_name, customer_phone FROM orders "
            "WHERE customer_phone_normalized=? ORDER BY created_at DESC, id DESC LIMIT 1",
            (normalized,),
        ).fetchone()
        address = conn.execute(
            "SELECT area_id, area_name, detailed_address FROM orders "
            "WHERE customer_phone_normalized=? AND fulfillment='DELIVERY' "
            "AND TRIM(COALESCE(detailed_address, ''))!='' "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (normalized,),
        ).fetchone()
        result["customer"] = {
            "name": identity["customer_name"] if identity else "",
            "phone": identity["customer_phone"] if identity else phone.strip(),
            "area_id": address["area_id"] if address else None,
            "area_name": address["area_name"] if address else "",
            "detailed_address": strip_area_prefix(
                address["detailed_address"], address["area_name"]
            ) if address else "",
        }
        return result


@app.post("/api/loyalty/reward-codes")
def create_reward_code(payload: RewardCodeInput) -> dict[str, Any]:
    if not valid_egyptian_mobile(payload.phone):
        raise HTTPException(
            status_code=422,
            detail="رقم الموبايل لازم يكون 11 رقم ويبدأ بـ010 أو 011 أو 012 أو 015",
        )
    normalized = payload.phone.strip()
    now = utc_now()
    code = f"BROOST-{secrets.token_hex(6).upper()}"
    with db_connection(immediate=True) as conn:
        adjust_loyalty_account(conn, normalized, 0)
        reserved = conn.execute(
            "UPDATE loyalty_accounts SET points_balance=points_balance-?, updated_at=? "
            "WHERE phone_normalized=? AND points_balance>=?",
            (LOYALTY_REWARD_POINTS, now, normalized, LOYALTY_REWARD_POINTS),
        )
        if reserved.rowcount != 1:
            raise HTTPException(status_code=409, detail="رصيد النقاط أقل من 100 نقطة")
        try:
            conn.execute(
                "INSERT INTO reward_codes "
                "(code, phone_normalized, value, points_cost, status, created_at) "
                "VALUES (?, ?, ?, ?, 'ACTIVE', ?)",
                (
                    code, normalized, float(LOYALTY_REWARD_CODE_VALUE),
                    LOYALTY_REWARD_POINTS, now,
                ),
            )
        except (sqlite3.IntegrityError, DatabaseIntegrityError):
            raise HTTPException(status_code=409, detail="تعذر إنشاء الكود؛ حاول مرة أخرى")
        return loyalty_profile(conn, normalized)


@app.get("/api/customer/orders")
def public_customer_orders(phone: str = Query(min_length=7, max_length=30)) -> dict[str, Any]:
    if not valid_egyptian_mobile(phone):
        raise HTTPException(
            status_code=422,
            detail="رقم الموبايل لازم يكون 11 رقم ويبدأ بـ010 أو 011 أو 012 أو 015",
        )
    normalized = phone.strip()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE source='ONLINE' AND customer_phone_normalized=? "
            "ORDER BY created_at DESC, id DESC LIMIT 50",
            (normalized,),
        ).fetchall()
        return {
            "orders": [public_order_to_dict(conn, row) for row in rows],
            "loyalty": loyalty_profile(conn, normalized),
        }


@app.post("/api/orders")
def create_order(payload: CreateOrderInput) -> JSONResponse:
    with db_connection(immediate=True) as conn:
        existing = conn.execute(
            "SELECT * FROM orders WHERE client_request_id=?", (payload.client_request_id,)
        ).fetchone()
        if existing:
            return JSONResponse(public_order_to_dict(conn, existing), status_code=200)

        if not ordering_is_available(conn):
            raise HTTPException(
                status_code=409,
                detail="المطعم مغلق حاليًا. تقدر تشوف المنيو والأسعار وترجع تطلب وقت ما الكاشير يفتح.",
            )

        customer_name = payload.customer_name.strip()
        customer_phone_normalized = payload.customer_phone.strip()
        if len(customer_name) < 2:
            raise HTTPException(status_code=422, detail="اسم العميل غير صالح")
        if not valid_egyptian_mobile(customer_phone_normalized):
            raise HTTPException(
                status_code=422,
                detail="رقم الموبايل لازم يكون 11 رقم ويبدأ بـ010 أو 011 أو 012 أو 015",
            )

        area_id = None
        area_name = ""
        delivery_fee = 0.0
        address = payload.detailed_address.strip()
        if payload.fulfillment == "DELIVERY":
            if not payload.area_id:
                raise HTTPException(status_code=422, detail="اختيار القرية إجباري للدليفري")
            area = conn.execute(
                "SELECT id, name, delivery_fee FROM delivery_areas "
                "WHERE id=? AND is_active=1 AND delivery_enabled=1",
                (payload.area_id,),
            ).fetchone()
            if not area:
                raise HTTPException(status_code=409, detail="التوصيل للقرية المختارة متوقف حاليًا")
            area_id = area["id"]
            area_name = area["name"]
            delivery_fee = float(area["delivery_fee"])
            address = strip_area_prefix(address, area_name)
            if not address:
                raise HTTPException(status_code=422, detail="العنوان بالتفصيل إجباري للدليفري")

        wallet_number = setting(conn, "wallet_number", "").strip()
        if payload.payment_method == "WALLET" and not wallet_number:
            raise HTTPException(status_code=409, detail="الدفع بالمحفظة غير متاح حاليًا")

        calculated_items: list[dict[str, Any]] = []
        subtotal = 0.0
        for requested in payload.items:
            if bool(requested.item_id) == bool(requested.offer_id):
                raise HTTPException(status_code=422, detail="كل سطر طلب لازم يكون صنف أو عرض واحد")
            if len(requested.extra_ids) != len(set(requested.extra_ids)):
                raise HTTPException(status_code=422, detail="لا يمكن تكرار نفس الإضافة في سطر واحد")

            if requested.offer_id:
                offer = conn.execute(
                    "SELECT * FROM offers WHERE sync_id=? AND is_deleted=0 AND is_active=1",
                    (requested.offer_id,),
                ).fetchone()
                components = conn.execute(
                    """
                    SELECT oi.quantity, mi.sync_id, mi.name, mi.base_price,
                           mi.is_available, mi.is_deleted
                    FROM offer_items oi
                    JOIN menu_items mi ON mi.sync_id=oi.item_sync_id
                    WHERE oi.offer_sync_id=?
                    ORDER BY oi.local_id, oi.sync_id
                    """,
                    (requested.offer_id,),
                ).fetchall()
                if (
                    not offer
                    or not components
                    or any(not part["is_available"] or part["is_deleted"] for part in components)
                ):
                    raise HTTPException(status_code=409, detail="العرض لم يعد متاحًا")
                if requested.size_id or requested.extra_ids or requested.spicy:
                    raise HTTPException(status_code=422, detail="لا يمكن تغيير مكونات العرض")

                unit_price = float(offer["offer_price"])
                component_extras = [
                    {
                        "name": f"{int(part['quantity'])}× {part['name']}",
                        "price": 0.0,
                        "system_key": "offer_component",
                    }
                    for part in components
                ]
                subtotal += unit_price * requested.quantity
                calculated_items.append({
                    "menu_item_sync_id": None,
                    "item_name": f"عرض: {offer['name']}",
                    "size_name": "باكدج",
                    "quantity": requested.quantity,
                    "unit_price": unit_price,
                    "extras": component_extras,
                })
                continue

            item = conn.execute(
                "SELECT * FROM menu_items WHERE sync_id=? AND is_deleted=0 AND is_available=1",
                (requested.item_id,),
            ).fetchone()
            if not item:
                raise HTTPException(status_code=409, detail="أحد الأصناف لم يعد متاحًا")

            unit_price = float(item["base_price"])
            size_name = "عادي"
            if requested.size_id:
                size = conn.execute(
                    "SELECT * FROM menu_item_sizes WHERE sync_id=? AND item_sync_id=?",
                    (requested.size_id, requested.item_id),
                ).fetchone()
                if not size:
                    raise HTTPException(status_code=409, detail=f"الحجم المختار غير متاح للصنف {item['name']}")
                size_name = size["name"]
                unit_price += float(size["price_offset"])

            extras: list[dict[str, Any]] = []
            for extra_id in requested.extra_ids:
                extra = conn.execute(
                    "SELECT * FROM menu_item_extras WHERE sync_id=? AND item_sync_id=?",
                    (extra_id, requested.item_id),
                ).fetchone()
                if not extra:
                    raise HTTPException(status_code=409, detail=f"إضافة غير متاحة للصنف {item['name']}")
                extra_price = float(extra["price"])
                unit_price += extra_price
                extras.append({"name": extra["name"], "price": extra_price})
            if requested.spicy:
                extras.append({"name": "حار", "price": 0.0, "system_key": "spicy"})

            line_total = unit_price * requested.quantity
            subtotal += line_total
            calculated_items.append({
                "menu_item_sync_id": item["sync_id"],
                "item_name": item["name"],
                "size_name": size_name,
                "quantity": requested.quantity,
                "unit_price": unit_price,
                "extras": extras,
            })

        subtotal = round(subtotal, 2)
        delivery_fee = round(delivery_fee, 2)
        discount = 0.0
        redeemed_points = 0
        normalized_reward_code = payload.reward_code.strip().upper()
        if normalized_reward_code:
            reward = conn.execute(
                "SELECT code, value FROM reward_codes WHERE code=? AND phone_normalized=? "
                "AND status='ACTIVE'",
                (normalized_reward_code, customer_phone_normalized),
            ).fetchone()
            if not reward:
                raise HTTPException(
                    status_code=409,
                    detail="كود المكافأة غير صحيح أو مستخدم أو لا يخص رقم الموبايل ده",
                )
            discount = min(subtotal, float(reward["value"]))
        elif payload.redeem_reward:
            if Decimal(str(subtotal)) > LOYALTY_REWARD_MAX_SUBTOTAL:
                raise HTTPException(
                    status_code=409,
                    detail="مكافأة الـ100 نقطة متاحة لأوردر منتجات بـ150 جنيه أو أقل",
                )
            if loyalty_profile(conn, customer_phone_normalized)["points"] < LOYALTY_REWARD_POINTS:
                raise HTTPException(status_code=409, detail="رصيد النقاط أقل من 100 نقطة")
            discount = subtotal
            redeemed_points = LOYALTY_REWARD_POINTS

        discount = round(discount, 2)
        total = round(subtotal - discount + delivery_fee, 2)
        payment_status = (
            "CONFIRMED"
            if total <= 0
            else "AWAITING_PAYMENT"
            if payload.payment_method == "WALLET"
            else ("CASH_ON_DELIVERY" if payload.fulfillment == "DELIVERY" else "CASH_ON_PICKUP")
        )
        now = utc_now()
        token = secrets.token_urlsafe(32)
        cursor = conn.execute(
            """
            INSERT INTO orders (
                resume_token, client_request_id, source, fulfillment, customer_name,
                customer_phone, customer_phone_normalized, area_id, area_name, detailed_address, payment_method,
                payment_status, status, subtotal, delivery_fee, discount, total, notes,
                loyalty_points_redeemed, reward_code, created_at, updated_at
            ) VALUES (?, ?, 'ONLINE', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token, payload.client_request_id, payload.fulfillment,
                customer_name, payload.customer_phone.strip(),
                customer_phone_normalized, area_id,
                area_name, address, payload.payment_method, payment_status, subtotal,
                delivery_fee, discount, total, payload.notes.strip(), redeemed_points,
                normalized_reward_code or None, now, now,
            ),
        )
        order_id = cursor.lastrowid
        if normalized_reward_code:
            code_reservation = conn.execute(
                "UPDATE reward_codes SET status='RESERVED', reserved_order_id=?, reserved_at=? "
                "WHERE code=? AND phone_normalized=? AND status='ACTIVE'",
                (order_id, now, normalized_reward_code, customer_phone_normalized),
            )
            if code_reservation.rowcount != 1:
                raise HTTPException(status_code=409, detail="كود المكافأة لم يعد متاحًا")
        if redeemed_points:
            reserve = conn.execute(
                "UPDATE loyalty_accounts SET points_balance=points_balance-?, updated_at=? "
                "WHERE phone_normalized=? AND points_balance>=?",
                (
                    redeemed_points, now, customer_phone_normalized,
                    LOYALTY_REWARD_POINTS,
                ),
            )
            if reserve.rowcount != 1:
                raise HTTPException(status_code=409, detail="رصيد النقاط لم يعد كافيًا للمكافأة")
            record_loyalty_transaction(
                conn, customer_phone_normalized, order_id, "REDEEM", -redeemed_points
            )
        public_number = f"WEB-{order_id:05d}"
        conn.execute("UPDATE orders SET public_number=? WHERE id=?", (public_number, order_id))
        conn.executemany(
            """
            INSERT INTO order_items (
                order_id, menu_item_sync_id, item_name, size_name, quantity, unit_price, extras_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order_id, item["menu_item_sync_id"], item["item_name"], item["size_name"],
                    item["quantity"], item["unit_price"], json.dumps(item["extras"], ensure_ascii=False),
                )
                for item in calculated_items
            ],
        )
        emit_event(conn, order_id, "ORDER_CREATED", {"public_number": public_number})
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        response = public_order_to_dict(conn, row)
        if payload.payment_method == "WALLET":
            response["wallet_number"] = wallet_number
        return JSONResponse(response, status_code=201)


@app.get("/api/orders/{resume_token}")
def get_public_order(resume_token: str) -> dict[str, Any]:
    with db_connection() as conn:
        row = conn.execute("SELECT * FROM orders WHERE resume_token=?", (resume_token,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")
        response = public_order_to_dict(conn, row)
        if row["payment_method"] == "WALLET" and row["payment_status"] in (
            "AWAITING_PAYMENT", "REJECTED"
        ):
            response["wallet_number"] = setting(conn, "wallet_number", "")
        return response


@app.post("/api/orders/{resume_token}/cancel")
def cancel_public_order(resume_token: str) -> dict[str, Any]:
    """Let the customer cancel safely until the order leaves for delivery."""
    with db_connection(immediate=True) as conn:
        row = conn.execute("SELECT * FROM orders WHERE resume_token=?", (resume_token,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")
        if row["status"] == "CANCELLED":
            return public_order_to_dict(conn, row)
        if row["status"] not in ("NEW", "ACCEPTED", "PREPARING", "READY"):
            raise HTTPException(
                status_code=409,
                detail="لا يمكن إلغاء الطلب بعد خروجه للتوصيل أو اكتماله. اتصل بالمطعم للمساعدة.",
            )

        now = utc_now()
        conn.execute(
            "UPDATE orders SET status='CANCELLED', cancelled_by='CUSTOMER', "
            "closed_at=?, updated_at=? WHERE id=?",
            (now, now, row["id"]),
        )
        reconcile_order_loyalty(conn, row["id"])
        emit_event(
            conn,
            row["id"],
            "ORDER_CANCELLED_BY_CUSTOMER",
            {"public_number": row["public_number"]},
        )
        updated = conn.execute("SELECT * FROM orders WHERE id=?", (row["id"],)).fetchone()
        return public_order_to_dict(conn, updated)


def store_payment_proof(raw: bytes, filename: str) -> tuple[str | None, str | None]:
    """Store a payment proof remotely in production and locally in development."""
    if CLOUDINARY_URL:
        try:
            result = cloudinary.uploader.upload(
                io.BytesIO(raw),
                resource_type="image",
                folder="cashier-system/payment-proofs",
                public_id=Path(filename).stem[:80],
                overwrite=False,
                unique_filename=False,
            )
            proof_url = str(result.get("secure_url") or "")
            storage_id = str(result.get("public_id") or "")
            if not proof_url or not storage_id:
                raise ValueError("Cloudinary returned incomplete upload data")
            return proof_url, storage_id
        except (CloudinaryError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=502,
                detail="تعذر رفع صورة التحويل حاليًا؛ حاول مرة أخرى بعد قليل",
            ) from exc

    if APP_ENV == "production":
        raise HTTPException(status_code=503, detail="خدمة حفظ صور التحويل غير مهيأة")
    destination = PROOFS_DIR / filename
    if not destination.exists():
        destination.write_bytes(raw)
    return None, None


def payment_proof_response(row: Any) -> Response:
    proof_url = str(row["proof_url"] or "") if "proof_url" in row.keys() else ""
    if proof_url:
        try:
            response = httpx.get(proof_url, follow_redirects=True, timeout=25.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="تعذر تحميل صورة التحويل") from exc
        return Response(content=response.content, media_type=row["proof_mime_type"])

    path = PROOFS_DIR / row["proof_filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="ملف إثبات التحويل غير موجود")
    return FileResponse(
        path,
        media_type=row["proof_mime_type"],
        filename=row["proof_original_name"],
    )


@app.post("/api/orders/{resume_token}/proof")
def upload_payment_proof(resume_token: str, payload: ProofInput) -> dict[str, Any]:
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="ملف إثبات التحويل غير صالح")
    if not raw or len(raw) > MAX_PROOF_BYTES:
        raise HTTPException(status_code=413, detail="حجم الصورة يجب ألا يتجاوز 6 ميجابايت")

    detected_mime = (
        "image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n")
        else "image/jpeg" if raw.startswith(b"\xff\xd8\xff")
        else "image/webp" if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"
        else ""
    )
    if detected_mime != payload.mime_type:
        raise HTTPException(status_code=422, detail="محتوى صورة التحويل لا يطابق نوع الملف")
    transfer_suffix = payload.transfer_phone_suffix.strip()
    if not re.fullmatch(r"[0-9]{4}", transfer_suffix):
        raise HTTPException(status_code=422, detail="اكتب آخر 4 أرقام من رقم المحفظة المحول منها")

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[payload.mime_type]

    with db_connection(immediate=True) as conn:
        row = conn.execute("SELECT * FROM orders WHERE resume_token=?", (resume_token,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")
        if row["payment_method"] != "WALLET":
            raise HTTPException(status_code=409, detail="هذا الطلب ليس طلب محفظة")
        digest = hashlib.sha256(raw).hexdigest()
        filename = f"{row['id']}_{digest[:20]}{extension}"
        if row["status"] == "CANCELLED":
            raise HTTPException(status_code=409, detail="الطلب ملغي")
        if row["status"] != "NEW":
            raise HTTPException(status_code=409, detail="لا يمكن رفع تحويل بعد بدء تجهيز الطلب")
        if row["payment_status"] == "PROOF_UPLOADED":
            if row["proof_filename"] == filename:
                return public_order_to_dict(conn, row)
            raise HTTPException(status_code=409, detail="يوجد إثبات تحويل تحت المراجعة بالفعل")
        if row["payment_status"] == "CONFIRMED":
            raise HTTPException(status_code=409, detail="تم تأكيد التحويل بالفعل")
        if row["payment_status"] not in ("AWAITING_PAYMENT", "REJECTED"):
            raise HTTPException(status_code=409, detail="لا يمكن رفع إثبات في حالة الدفع الحالية")

        proof_url, proof_storage_id = store_payment_proof(raw, filename)

        now = utc_now()
        conn.execute(
            """
            UPDATE orders
            SET proof_filename=?, proof_original_name=?, proof_mime_type=?,
                proof_url=?, proof_storage_id=?, transfer_phone_suffix=?,
                payment_status='PROOF_UPLOADED', updated_at=?
            WHERE id=?
            """,
            (
                filename, Path(payload.filename).name, payload.mime_type,
                proof_url, proof_storage_id, transfer_suffix, now, row["id"],
            ),
        )
        emit_event(conn, row["id"], "PAYMENT_PROOF_UPLOADED", {"sha256": digest})
        updated = conn.execute("SELECT * FROM orders WHERE id=?", (row["id"],)).fetchone()
        return public_order_to_dict(conn, updated)


@app.post("/api/admin/login")
async def admin_login(request: Request) -> dict[str, bool]:
    data = await request.json()
    password = str(data.get("password", ""))
    with db_connection() as conn:
        expected = setting(conn, "admin_password", "9999")
    if not secrets.compare_digest(password, expected):
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة")
    return {"ok": True}


@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
def get_admin_settings() -> dict[str, Any]:
    with db_connection() as conn:
        return {
            "restaurant_name": setting(conn, "restaurant_name", "Broost"),
            "wallet_number": setting(conn, "wallet_number", ""),
            "ordering_enabled": setting(conn, "ordering_enabled", "1") == "1",
            "business_hours": setting(conn, "business_hours", ""),
            "branch_address": setting(conn, "branch_address", ""),
            "contact_phone": setting(conn, "contact_phone", ""),
            "whatsapp_number": setting(conn, "whatsapp_number", ""),
            "map_url": setting(conn, "map_url", ""),
            "facebook_url": setting(conn, "facebook_url", ""),
        }


@app.put("/api/admin/settings", dependencies=[Depends(require_admin)])
def update_admin_settings(payload: SettingsInput) -> dict[str, bool]:
    with db_connection() as conn:
        set_setting(conn, "restaurant_name", payload.restaurant_name.strip())
        set_setting(conn, "wallet_number", payload.wallet_number.strip())
        set_setting(conn, "ordering_enabled", "1" if payload.ordering_enabled else "0")
        set_setting(conn, "business_hours", payload.business_hours.strip())
        set_setting(conn, "branch_address", payload.branch_address.strip())
        set_setting(conn, "contact_phone", payload.contact_phone.strip())
        set_setting(conn, "whatsapp_number", payload.whatsapp_number.strip())
        set_setting(conn, "map_url", payload.map_url.strip())
        set_setting(conn, "facebook_url", payload.facebook_url.strip())
    return {"ok": True}


@app.get("/api/admin/reviews", dependencies=[Depends(require_admin)])
def list_admin_reviews() -> list[dict[str, Any]]:
    with db_connection() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM reviews ORDER BY sort_order, id DESC"
        ).fetchall()]


@app.post("/api/admin/reviews", dependencies=[Depends(require_admin)])
def create_admin_review(payload: ReviewInput) -> dict[str, Any]:
    now = utc_now()
    with db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO reviews (customer_name, review_text, rating, is_visible, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload.customer_name.strip(), payload.review_text.strip(), payload.rating,
                int(payload.is_visible), payload.sort_order, now, now,
            ),
        )
        return dict(conn.execute("SELECT * FROM reviews WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.patch("/api/admin/reviews/{review_id}", dependencies=[Depends(require_admin)])
def update_admin_review(review_id: int, payload: ReviewInput) -> dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE reviews SET customer_name=?, review_text=?, rating=?, is_visible=?, "
            "sort_order=?, updated_at=? WHERE id=?",
            (
                payload.customer_name.strip(), payload.review_text.strip(), payload.rating,
                int(payload.is_visible), payload.sort_order, utc_now(), review_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="الرأي غير موجود")
        return dict(conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone())


@app.delete("/api/admin/reviews/{review_id}", dependencies=[Depends(require_admin)])
def delete_admin_review(review_id: int) -> dict[str, bool]:
    with db_connection() as conn:
        cursor = conn.execute("DELETE FROM reviews WHERE id=?", (review_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="الرأي غير موجود")
    return {"ok": True}


@app.get("/api/admin/areas", dependencies=[Depends(require_admin)])
def list_admin_areas() -> list[dict[str, Any]]:
    with db_connection() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM delivery_areas ORDER BY sort_order, name"
        )]


@app.post("/api/admin/areas", dependencies=[Depends(require_admin)])
def create_admin_area(payload: AreaInput) -> dict[str, Any]:
    with db_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO delivery_areas "
                "(name, delivery_fee, is_active, delivery_enabled, sort_order, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    payload.name.strip(), payload.delivery_fee, int(payload.is_active),
                    int(payload.delivery_enabled), payload.sort_order, utc_now(),
                ),
            )
        except (sqlite3.IntegrityError, DatabaseIntegrityError):
            raise HTTPException(status_code=409, detail="اسم القرية موجود بالفعل")
        return dict(conn.execute("SELECT * FROM delivery_areas WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.patch("/api/admin/areas/{area_id}", dependencies=[Depends(require_admin)])
def update_admin_area(area_id: int, payload: AreaUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="لا توجد تعديلات")
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if "is_active" in changes:
        changes["is_active"] = int(changes["is_active"])
    if "delivery_enabled" in changes:
        changes["delivery_enabled"] = int(changes["delivery_enabled"])
    changes["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in changes)
    with db_connection() as conn:
        try:
            cursor = conn.execute(
                f"UPDATE delivery_areas SET {assignments} WHERE id=?",
                (*changes.values(), area_id),
            )
        except (sqlite3.IntegrityError, DatabaseIntegrityError):
            raise HTTPException(status_code=409, detail="اسم القرية موجود بالفعل")
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="القرية غير موجودة")
        return dict(conn.execute("SELECT * FROM delivery_areas WHERE id=?", (area_id,)).fetchone())


@app.delete("/api/admin/areas/{area_id}", dependencies=[Depends(require_admin)])
def disable_admin_area(area_id: int) -> dict[str, bool]:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE delivery_areas SET is_active=0, updated_at=? WHERE id=?",
            (utc_now(), area_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="القرية غير موجودة")
    return {"ok": True}


@app.get("/api/admin/menu", dependencies=[Depends(require_admin)])
def admin_menu() -> dict[str, Any]:
    with db_connection() as conn:
        return read_menu(conn, include_deleted=True)


@app.post("/api/admin/menu/categories", dependencies=[Depends(require_admin)])
def create_admin_category(payload: CategoryInput) -> dict[str, Any]:
    sync_id = f"web-category-{uuid.uuid4().hex}"
    now = utc_now()
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO categories (sync_id, name, sort_order, is_active, is_deleted, updated_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (sync_id, payload.name.strip(), payload.sort_order, int(payload.is_active), now),
        )
        bump_menu_version(conn)
        return dict(conn.execute("SELECT * FROM categories WHERE sync_id=?", (sync_id,)).fetchone())


@app.patch("/api/admin/menu/categories/{sync_id}", dependencies=[Depends(require_admin)])
def update_admin_category(sync_id: str, payload: CategoryInput) -> dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE categories SET name=?, sort_order=?, is_active=?, is_deleted=0, updated_at=? WHERE sync_id=?",
            (payload.name.strip(), payload.sort_order, int(payload.is_active), utc_now(), sync_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="القسم غير موجود")
        bump_menu_version(conn)
        return dict(conn.execute("SELECT * FROM categories WHERE sync_id=?", (sync_id,)).fetchone())


@app.delete("/api/admin/menu/categories/{sync_id}", dependencies=[Depends(require_admin)])
def delete_admin_category(sync_id: str) -> dict[str, bool]:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE categories SET is_deleted=1, is_active=0, updated_at=? WHERE sync_id=?",
            (utc_now(), sync_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="القسم غير موجود")
        conn.execute(
            "UPDATE menu_items SET is_deleted=1, is_available=0, updated_at=? WHERE category_sync_id=?",
            (utc_now(), sync_id),
        )
        bump_menu_version(conn)
    return {"ok": True}


def replace_item_options(
    conn: sqlite3.Connection,
    item_sync_id: str,
    sizes: list[MenuOptionInput],
    extras: list[MenuOptionInput],
) -> None:
    conn.execute("DELETE FROM menu_item_sizes WHERE item_sync_id=?", (item_sync_id,))
    conn.execute("DELETE FROM menu_item_extras WHERE item_sync_id=?", (item_sync_id,))
    now = utc_now()
    conn.executemany(
        "INSERT INTO menu_item_sizes (sync_id, item_sync_id, name, price_offset, updated_at) VALUES (?, ?, ?, ?, ?)",
        [(f"web-size-{uuid.uuid4().hex}", item_sync_id, opt.name.strip(), opt.price, now) for opt in sizes],
    )
    conn.executemany(
        "INSERT INTO menu_item_extras (sync_id, item_sync_id, name, price, updated_at) VALUES (?, ?, ?, ?, ?)",
        [(f"web-extra-{uuid.uuid4().hex}", item_sync_id, opt.name.strip(), opt.price, now) for opt in extras],
    )


@app.post("/api/admin/menu/items", dependencies=[Depends(require_admin)])
def create_admin_item(payload: MenuItemAdminInput) -> dict[str, Any]:
    sync_id = f"web-item-{uuid.uuid4().hex}"
    now = utc_now()
    with db_connection() as conn:
        category = conn.execute(
            "SELECT sync_id FROM categories WHERE sync_id=? AND is_deleted=0",
            (payload.category_sync_id,),
        ).fetchone()
        if not category:
            raise HTTPException(status_code=409, detail="القسم المختار غير موجود")
        conn.execute(
            """
            INSERT INTO menu_items (
                sync_id, category_sync_id, name, base_price, is_available, is_popular,
                is_daily_offer, is_deleted, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                sync_id, payload.category_sync_id, payload.name.strip(), payload.base_price,
                int(payload.is_available), int(payload.is_popular), int(payload.is_daily_offer), now,
            ),
        )
        replace_item_options(conn, sync_id, payload.sizes, payload.extras)
        bump_menu_version(conn)
        return dict(conn.execute("SELECT * FROM menu_items WHERE sync_id=?", (sync_id,)).fetchone())


@app.patch("/api/admin/menu/items/{sync_id}", dependencies=[Depends(require_admin)])
def update_admin_item(sync_id: str, payload: MenuItemAdminInput) -> dict[str, Any]:
    with db_connection() as conn:
        category = conn.execute(
            "SELECT sync_id FROM categories WHERE sync_id=? AND is_deleted=0",
            (payload.category_sync_id,),
        ).fetchone()
        if not category:
            raise HTTPException(status_code=409, detail="القسم المختار غير موجود")
        cursor = conn.execute(
            """
            UPDATE menu_items SET category_sync_id=?, name=?, base_price=?, is_available=?,
                is_popular=?, is_daily_offer=?, is_deleted=0, updated_at=? WHERE sync_id=?
            """,
            (
                payload.category_sync_id, payload.name.strip(), payload.base_price,
                int(payload.is_available), int(payload.is_popular), int(payload.is_daily_offer),
                utc_now(), sync_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="الصنف غير موجود")
        replace_item_options(conn, sync_id, payload.sizes, payload.extras)
        bump_menu_version(conn)
        return dict(conn.execute("SELECT * FROM menu_items WHERE sync_id=?", (sync_id,)).fetchone())


@app.delete("/api/admin/menu/items/{sync_id}", dependencies=[Depends(require_admin)])
def delete_admin_item(sync_id: str) -> dict[str, bool]:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE menu_items SET is_deleted=1, is_available=0, updated_at=? WHERE sync_id=?",
            (utc_now(), sync_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="الصنف غير موجود")
        bump_menu_version(conn)
    return {"ok": True}


def replace_offer_components(
    conn: sqlite3.Connection,
    offer_sync_id: str,
    components: list[OfferComponentInput],
) -> float:
    combined: dict[str, int] = {}
    for component in components:
        combined[component.item_sync_id] = combined.get(component.item_sync_id, 0) + component.quantity

    placeholders = ",".join("?" for _ in combined)
    rows = conn.execute(
        f"SELECT sync_id, base_price FROM menu_items "
        f"WHERE sync_id IN ({placeholders}) AND is_deleted=0",
        tuple(combined),
    ).fetchall()
    prices = {row["sync_id"]: float(row["base_price"]) for row in rows}
    if len(prices) != len(combined):
        raise HTTPException(status_code=409, detail="أحد أصناف العرض غير موجود")

    conn.execute("DELETE FROM offer_items WHERE offer_sync_id=?", (offer_sync_id,))
    now = utc_now()
    conn.executemany(
        "INSERT INTO offer_items "
        "(sync_id, offer_sync_id, item_sync_id, quantity, updated_at) VALUES (?, ?, ?, ?, ?)",
        [
            (f"web-offer-item-{uuid.uuid4().hex}", offer_sync_id, item_id, quantity, now)
            for item_id, quantity in combined.items()
        ],
    )
    return sum(prices[item_id] * quantity for item_id, quantity in combined.items())


@app.post("/api/admin/offers", dependencies=[Depends(require_admin)])
def create_admin_offer(payload: OfferAdminInput) -> dict[str, Any]:
    sync_id = f"web-offer-{uuid.uuid4().hex}"
    now = utc_now()
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO offers "
            "(sync_id, name, offer_price, is_active, is_deleted, updated_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (sync_id, payload.name.strip(), payload.offer_price, int(payload.is_active), now),
        )
        regular_price = replace_offer_components(conn, sync_id, payload.items)
        if payload.offer_price >= regular_price:
            raise HTTPException(status_code=422, detail="سعر العرض لازم يكون أقل من السعر الأصلي")
        bump_menu_version(conn)
        result = dict(conn.execute("SELECT * FROM offers WHERE sync_id=?", (sync_id,)).fetchone())
        result["regular_price"] = regular_price
        return result


@app.patch("/api/admin/offers/{sync_id}", dependencies=[Depends(require_admin)])
def update_admin_offer(sync_id: str, payload: OfferAdminInput) -> dict[str, Any]:
    with db_connection() as conn:
        if not conn.execute("SELECT 1 FROM offers WHERE sync_id=?", (sync_id,)).fetchone():
            raise HTTPException(status_code=404, detail="العرض غير موجود")
        regular_price = replace_offer_components(conn, sync_id, payload.items)
        if payload.offer_price >= regular_price:
            raise HTTPException(status_code=422, detail="سعر العرض لازم يكون أقل من السعر الأصلي")
        conn.execute(
            "UPDATE offers SET name=?, offer_price=?, is_active=?, is_deleted=0, updated_at=? "
            "WHERE sync_id=?",
            (payload.name.strip(), payload.offer_price, int(payload.is_active), utc_now(), sync_id),
        )
        bump_menu_version(conn)
        result = dict(conn.execute("SELECT * FROM offers WHERE sync_id=?", (sync_id,)).fetchone())
        result["regular_price"] = regular_price
        return result


@app.delete("/api/admin/offers/{sync_id}", dependencies=[Depends(require_admin)])
def delete_admin_offer(sync_id: str) -> dict[str, bool]:
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE offers SET is_deleted=1, is_active=0, updated_at=? WHERE sync_id=?",
            (utc_now(), sync_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="العرض غير موجود")
        bump_menu_version(conn)
    return {"ok": True}


@app.get("/api/admin/orders", dependencies=[Depends(require_admin)])
def admin_orders(
    date_from: str | None = None,
    date_to: str | None = None,
    source: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("created_at < ?")
        try:
            params.append((datetime.fromisoformat(date_to) + timedelta(days=1)).date().isoformat())
        except ValueError:
            raise HTTPException(status_code=422, detail="تاريخ النهاية غير صحيح")
    if source:
        clauses.append("source=?")
        params.append(source.upper())
    if status:
        clauses.append("status=?")
        params.append(status.upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM orders {where} ORDER BY created_at DESC LIMIT 1000", params
        ).fetchall()
        return [order_to_dict(conn, row) for row in rows]


@app.get("/api/admin/customers", dependencies=[Depends(require_admin)])
def admin_customers(query: str = "", limit: int = Query(default=250, ge=1, le=1000)) -> list[dict[str, Any]]:
    query = query.strip()
    normalized_query = normalize_phone(query)
    clauses = ["customer_phone_normalized IS NOT NULL", "customer_phone_normalized!=''"]
    params: list[Any] = []
    if query:
        clauses.append("(customer_name LIKE ? OR customer_phone LIKE ? OR customer_phone_normalized LIKE ?)")
        params.extend((f"%{query}%", f"%{query}%", f"%{normalized_query or query}%"))
    with db_connection() as conn:
        phones = conn.execute(
            f"SELECT customer_phone_normalized, MAX(created_at) AS last_order_at "
            f"FROM orders WHERE {' AND '.join(clauses)} "
            "GROUP BY customer_phone_normalized ORDER BY last_order_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for phone_row in phones:
            latest = conn.execute(
                "SELECT customer_name, customer_phone FROM orders "
                "WHERE customer_phone_normalized=? ORDER BY created_at DESC LIMIT 1",
                (phone_row["customer_phone_normalized"],),
            ).fetchone()
            summary = customer_reliability(conn, phone_row["customer_phone_normalized"])
            points = loyalty_profile(conn, phone_row["customer_phone_normalized"])
            result.append({
                "customer_name": latest["customer_name"] if latest else "عميل",
                "customer_phone": latest["customer_phone"] if latest else phone_row["customer_phone_normalized"],
                "phone_normalized": phone_row["customer_phone_normalized"],
                "loyalty_points": points["points"],
                "reward_available": points["reward_available"],
                **summary,
            })
        return result


@app.get("/api/admin/customers/{phone}", dependencies=[Depends(require_admin)])
def admin_customer_profile(phone: str) -> dict[str, Any]:
    normalized = normalize_phone(phone)
    if not normalized:
        raise HTTPException(status_code=422, detail="رقم الهاتف غير صالح")
    with db_connection() as conn:
        orders = conn.execute(
            "SELECT * FROM orders WHERE customer_phone_normalized=? "
            "ORDER BY created_at DESC LIMIT 50",
            (normalized,),
        ).fetchall()
        if not orders:
            raise HTTPException(status_code=404, detail="لا يوجد عميل بهذا الرقم")
        return {
            "customer_name": orders[0]["customer_name"],
            "customer_phone": orders[0]["customer_phone"],
            "reliability": customer_reliability(conn, normalized),
            "loyalty": loyalty_profile(conn, normalized),
            "issues": customer_issue_rows(conn, normalized),
            "orders": [order_to_dict(conn, row) for row in orders],
        }


@app.post("/api/admin/orders/{order_id}/customer-issues", dependencies=[Depends(require_admin)])
def create_customer_issue(order_id: int, payload: CustomerIssueInput) -> dict[str, Any]:
    with db_connection() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")
        normalized = order["customer_phone_normalized"] or normalize_phone(order["customer_phone"])
        if not normalized:
            raise HTTPException(status_code=409, detail="لا يمكن تسجيل ملاحظة بدون رقم هاتف")
        cursor = conn.execute(
            "INSERT INTO customer_issues (phone_normalized, order_id, issue_type, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (normalized, order_id, payload.issue_type, payload.note.strip(), utc_now()),
        )
        emit_event(conn, order_id, "CUSTOMER_RELIABILITY_UPDATED", {"issue_id": cursor.lastrowid})
        return {
            "reliability": customer_reliability(conn, normalized),
            "issues": customer_issue_rows(conn, normalized),
        }


@app.patch("/api/admin/customer-issues/{issue_id}", dependencies=[Depends(require_admin)])
def update_customer_issue(issue_id: int, payload: CustomerIssueUpdate) -> dict[str, Any]:
    with db_connection() as conn:
        issue = conn.execute("SELECT * FROM customer_issues WHERE id=?", (issue_id,)).fetchone()
        if not issue:
            raise HTTPException(status_code=404, detail="الملاحظة غير موجودة")
        conn.execute(
            "UPDATE customer_issues SET is_resolved=?, resolved_at=? WHERE id=?",
            (int(payload.is_resolved), utc_now() if payload.is_resolved else None, issue_id),
        )
        if issue["order_id"]:
            emit_event(conn, issue["order_id"], "CUSTOMER_RELIABILITY_UPDATED", {"issue_id": issue_id})
        return {
            "reliability": customer_reliability(conn, issue["phone_normalized"]),
            "issues": customer_issue_rows(conn, issue["phone_normalized"]),
        }


@app.delete("/api/admin/customer-issues/{issue_id}", dependencies=[Depends(require_admin)])
def delete_customer_issue(issue_id: int) -> dict[str, bool]:
    with db_connection() as conn:
        issue = conn.execute("SELECT * FROM customer_issues WHERE id=?", (issue_id,)).fetchone()
        if not issue:
            raise HTTPException(status_code=404, detail="الملاحظة غير موجودة")
        conn.execute("DELETE FROM customer_issues WHERE id=?", (issue_id,))
        if issue["order_id"]:
            emit_event(conn, issue["order_id"], "CUSTOMER_RELIABILITY_UPDATED", {"issue_id": issue_id})
    return {"ok": True}


@app.patch("/api/admin/orders/{order_id}", dependencies=[Depends(require_admin)])
def update_admin_order(order_id: int, payload: OrderAdminUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="لا توجد تعديلات")
    if changes.get("status") == "ACCEPTED":
        changes["status"] = "PREPARING"
    with db_connection(immediate=True) as conn:
        existing = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="الطلب غير موجود")

        validate_order_changes(existing, changes)
        requested_status = changes.get("status")
        current_status = "PREPARING" if existing["status"] == "ACCEPTED" else existing["status"]
        if requested_status == current_status:
            changes.pop("status", None)

        if changes:
            changes["updated_at"] = utc_now()
            if requested_status in ("COMPLETED", "CANCELLED"):
                changes["closed_at"] = utc_now()
            if requested_status == "CANCELLED" and current_status != "CANCELLED":
                changes["cancelled_by"] = "CASHIER"
            assignments = ", ".join(f"{key}=?" for key in changes)
            conn.execute(
                f"UPDATE orders SET {assignments} WHERE id=?", (*changes.values(), order_id)
            )
        reconcile_order_loyalty(conn, order_id)
        if changes:
            emit_event(conn, order_id, "ORDER_UPDATED", changes)
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return order_to_dict(conn, row)


@app.get("/api/admin/orders/{order_id}/proof", dependencies=[Depends(require_admin)])
def get_admin_proof(order_id: int) -> Response:
    with db_connection() as conn:
        row = conn.execute(
            "SELECT proof_filename, proof_original_name, proof_mime_type, proof_url "
            "FROM orders WHERE id=?",
            (order_id,),
        ).fetchone()
        if not row or not row["proof_filename"]:
            raise HTTPException(status_code=404, detail="لا يوجد إثبات تحويل لهذا الطلب")
        return payment_proof_response(row)


@app.get("/api/sync/menu", dependencies=[Depends(require_sync)])
def sync_get_menu() -> dict[str, Any]:
    with db_connection() as conn:
        return read_menu(conn, include_deleted=True)


@app.post("/api/sync/menu", dependencies=[Depends(require_sync)])
def sync_post_menu(payload: SyncMenuInput) -> dict[str, Any]:
    now = utc_now()
    with db_connection() as conn:
        server_version = int(setting(conn, "menu_version", "0"))
        has_server_menu = conn.execute("SELECT 1 FROM categories LIMIT 1").fetchone() is not None
        if has_server_menu and payload.known_server_version != server_version:
            return {"accepted": False, "reason": "VERSION_CONFLICT", **read_menu(conn, include_deleted=True)}

        conn.execute("DELETE FROM offer_items")
        conn.execute("DELETE FROM offers")
        conn.execute("DELETE FROM menu_item_sizes")
        conn.execute("DELETE FROM menu_item_extras")
        conn.execute("DELETE FROM menu_items")
        conn.execute("DELETE FROM categories")

        for category in payload.categories:
            conn.execute(
                """
                INSERT INTO categories (
                    sync_id, local_id, name, sort_order, is_active, is_deleted, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category["sync_id"], category.get("local_id"), category["name"],
                    int(category.get("sort_order", 0)), int(category.get("is_active", 1)),
                    int(category.get("is_deleted", 0)), now,
                ),
            )
        for item in payload.items:
            conn.execute(
                """
                INSERT INTO menu_items (
                    sync_id, local_id, category_sync_id, name, base_price,
                    is_available, is_popular, is_daily_offer, is_deleted, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["sync_id"], item.get("local_id"), item["category_sync_id"], item["name"],
                    float(item.get("base_price", 0)), int(item.get("is_available", 1)),
                    int(item.get("is_popular", 0)), int(item.get("is_daily_offer", 0)),
                    int(item.get("is_deleted", 0)), now,
                ),
            )
        for size in payload.sizes:
            conn.execute(
                "INSERT INTO menu_item_sizes (sync_id, local_id, item_sync_id, name, price_offset, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    size["sync_id"], size.get("local_id"), size["item_sync_id"], size["name"],
                    float(size.get("price_offset", 0)), now,
                ),
            )
        for extra in payload.extras:
            conn.execute(
                "INSERT INTO menu_item_extras (sync_id, local_id, item_sync_id, name, price, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    extra["sync_id"], extra.get("local_id"), extra["item_sync_id"], extra["name"],
                    float(extra.get("price", 0)), now,
                ),
            )
        for offer in payload.offers:
            conn.execute(
                "INSERT INTO offers "
                "(sync_id, local_id, name, offer_price, is_active, is_deleted, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    offer["sync_id"], offer.get("local_id"), offer["name"],
                    float(offer.get("offer_price", 0)), int(offer.get("is_active", 1)),
                    int(offer.get("is_deleted", 0)), now,
                ),
            )
        for component in payload.offer_items:
            conn.execute(
                "INSERT INTO offer_items "
                "(sync_id, local_id, offer_sync_id, item_sync_id, quantity, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    component["sync_id"], component.get("local_id"),
                    component["offer_sync_id"], component["item_sync_id"],
                    int(component.get("quantity", 1)), now,
                ),
            )
        version = bump_menu_version(conn)
        return {"accepted": True, "version": version, "updated_at": now}


@app.get("/api/sync/events", dependencies=[Depends(require_sync)])
def sync_events(after: int = Query(default=0, ge=0)) -> dict[str, Any]:
    with db_connection() as conn:
        sync_epoch = setting(conn, "sync_epoch", "")
        server_last_row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS last_id FROM order_events"
        ).fetchone()
        server_last_event_id = int(server_last_row["last_id"] if server_last_row else 0)
        rows = conn.execute(
            "SELECT * FROM order_events WHERE id>? ORDER BY id LIMIT 200", (after,)
        ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json") or "{}")
            order = conn.execute("SELECT * FROM orders WHERE id=?", (row["order_id"],)).fetchone()
            event["order"] = order_to_dict(conn, order) if order else None
            events.append(event)
        return {
            "events": events,
            "last_event_id": events[-1]["id"] if events else min(after, server_last_event_id),
            "server_last_event_id": server_last_event_id,
            "sync_epoch": sync_epoch,
        }


@app.patch("/api/sync/orders/{order_id}", dependencies=[Depends(require_sync)])
def sync_update_order(order_id: int, payload: OrderAdminUpdate) -> dict[str, Any]:
    return update_admin_order(order_id, payload)


@app.get("/api/sync/orders/{order_id}/proof", dependencies=[Depends(require_sync)])
def sync_get_order_proof(order_id: int) -> Response:
    with db_connection() as conn:
        row = conn.execute(
            "SELECT proof_filename, proof_original_name, proof_mime_type, proof_url "
            "FROM orders WHERE id=?",
            (order_id,),
        ).fetchone()
        if not row or not row["proof_filename"]:
            raise HTTPException(status_code=404, detail="لا يوجد إثبات تحويل لهذا الطلب")
        return payment_proof_response(row)


@app.post("/api/sync/pos-orders", dependencies=[Depends(require_sync)])
def sync_pos_orders(payload: PosOrdersInput) -> dict[str, int]:
    synced = 0
    ignored = 0
    with db_connection(immediate=True) as conn:
        for order in payload.orders:
            remote_id = order.get("remote_id")
            if remote_id:
                existing = conn.execute(
                    "SELECT * FROM orders WHERE id=?", (remote_id,)
                ).fetchone()
                if not existing or existing["source"] != "ONLINE":
                    # Never manufacture a replacement customer order with a lost resume token
                    # or overwrite an unrelated row when a stale local remote_id is wrong.
                    ignored += 1
                    continue

                synced_status = order.get("status", existing["status"])
                if synced_status == "ACCEPTED":
                    synced_status = "PREPARING"
                online_changes = {
                    "status": synced_status,
                    "driver_name": order.get("driver_name") or "",
                    "cashier_name": order.get("cashier_name") or "",
                }
                try:
                    validate_order_changes(existing, online_changes)
                except HTTPException:
                    ignored += 1
                    reconcile_order_loyalty(conn, existing["id"])
                    continue

                current_status = (
                    "PREPARING" if existing["status"] == "ACCEPTED" else existing["status"]
                )
                updates: dict[str, Any] = {}
                local_order_id = order.get("local_order_id")
                if local_order_id != existing["local_order_id"]:
                    updates["local_order_id"] = local_order_id
                if synced_status != current_status:
                    updates["status"] = synced_status
                    if synced_status in ("COMPLETED", "CANCELLED"):
                        updates["closed_at"] = utc_now()
                    elif synced_status == "PREPARING":
                        updates["closed_at"] = None
                    if synced_status == "CANCELLED":
                        updates["cancelled_by"] = "CASHIER"
                for field in ("driver_name", "cashier_name"):
                    if online_changes[field] != (existing[field] or ""):
                        updates[field] = online_changes[field]

                if updates:
                    updates["updated_at"] = utc_now()
                    assignments = ", ".join(f"{key}=?" for key in updates)
                    conn.execute(
                        f"UPDATE orders SET {assignments} WHERE id=?",
                        (*updates.values(), existing["id"]),
                    )
                    emit_event(conn, existing["id"], "ORDER_UPDATED", updates)
                reconcile_order_loyalty(conn, existing["id"])
                synced += 1
                continue
            else:
                existing = conn.execute(
                    "SELECT * FROM orders "
                    "WHERE source='POS' AND local_order_id=?",
                    (order.get("local_order_id"),),
                ).fetchone()

            now = utc_now()
            synced_status = order.get("status", "NEW")
            if synced_status == "ACCEPTED":
                synced_status = "PREPARING"
            area_name = order.get("area_name") or ""
            values = {
                "source": "POS",
                "local_order_id": order.get("local_order_id"),
                "fulfillment": order.get("fulfillment", "PICKUP"),
                "customer_name": order.get("customer_name") or "عميل المطعم",
                "customer_phone": order.get("customer_phone") or "",
                "customer_phone_normalized": normalize_phone(order.get("customer_phone")),
                "area_name": area_name,
                "detailed_address": strip_area_prefix(order.get("detailed_address"), area_name),
                "payment_method": order.get("payment_method", "CASH"),
                "payment_status": order.get("payment_status") or (
                    "CONFIRMED" if order.get("payment_method") != "CASH" else "CASH_ON_PICKUP"
                ),
                "status": synced_status,
                "subtotal": float(order.get("subtotal", 0)),
                "delivery_fee": float(order.get("delivery_fee", 0)),
                "discount": float(order.get("discount", 0)),
                "total": float(order.get("total", 0)),
                "notes": order.get("notes") or "",
                "cashier_name": order.get("cashier_name") or "",
                "driver_name": order.get("driver_name") or "",
                "created_at": order.get("created_at") or now,
                "updated_at": now,
                "closed_at": order.get("closed_at"),
            }
            if existing:
                # The server owns canonical timestamps. A local POS copy may be
                # converted to Cairo time and must never overwrite them.
                values["created_at"] = existing["created_at"] or values["created_at"]
                values["closed_at"] = existing["closed_at"] or values["closed_at"]
                # A delayed local snapshot must not reopen terminal history.
                if existing["status"] == "CANCELLED":
                    values["status"] = "CANCELLED"
                elif existing["status"] == "COMPLETED" and values["status"] not in (
                    "COMPLETED", "CANCELLED"
                ):
                    values["status"] = "COMPLETED"
                order_id = existing["id"]
                assignments = ", ".join(f"{key}=?" for key in values)
                conn.execute(
                    f"UPDATE orders SET {assignments} WHERE id=?",
                    (*values.values(), order_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO orders (
                        public_number, resume_token, source, local_order_id, fulfillment,
                        customer_name, customer_phone, customer_phone_normalized, area_name, detailed_address,
                        payment_method, payment_status, status, subtotal, delivery_fee,
                        discount, total, notes, cashier_name, driver_name, created_at,
                        updated_at, closed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"POS-{int(order.get('local_order_id', 0)):05d}",
                        secrets.token_urlsafe(24),
                        *values.values(),
                    ),
                )
                order_id = cursor.lastrowid

            conn.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
            conn.executemany(
                """
                INSERT INTO order_items (
                    order_id, menu_item_sync_id, item_name, size_name, quantity, unit_price, extras_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        order_id, item.get("menu_item_sync_id"), item.get("item_name", ""),
                        item.get("size_name") or "عادي", int(item.get("quantity", 1)),
                        float(item.get("unit_price", 0)),
                        json.dumps(item.get("extras", []), ensure_ascii=False),
                    )
                    for item in order.get("items", [])
                ],
            )
            reconcile_order_loyalty(conn, order_id)
            synced += 1
    return {"synced": synced, "ignored": ignored}


@app.exception_handler(sqlite3.Error)
async def sqlite_error_handler(_: Request, exc: sqlite3.Error) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"خطأ في قاعدة البيانات: {exc}"})


@app.exception_handler(DatabaseError)
async def database_error_handler(_: Request, exc: DatabaseError) -> JSONResponse:
    # Keep connection details and SQL values out of public responses.
    return JSONResponse(status_code=500, content={"detail": "تعذر الاتصال بقاعدة البيانات"})
