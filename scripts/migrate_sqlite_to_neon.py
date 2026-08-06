# -*- coding: utf-8 -*-
"""One-time safe import of the current web SQLite database into an empty Neon DB."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if os.getenv("BROOST_LOAD_DOTENV", "1") != "0":
    load_dotenv(ROOT / ".env", override=False)


TABLES = [
    "settings",
    "delivery_areas",
    "categories",
    "menu_items",
    "menu_item_sizes",
    "menu_item_extras",
    "offers",
    "offer_items",
    "orders",
    "order_items",
    "order_events",
    "customer_issues",
    "reviews",
    "loyalty_accounts",
    "loyalty_transactions",
]
SERIAL_TABLES = [
    "delivery_areas",
    "orders",
    "order_items",
    "order_events",
    "customer_issues",
    "reviews",
    "loyalty_transactions",
]


def sqlite_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sqlite_path",
        nargs="?",
        type=Path,
        default=ROOT / "webapp" / "data" / "broost_web.db",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        parser.error("Set DATABASE_URL to the pooled Neon PostgreSQL URL first.")
    if not args.sqlite_path.is_file():
        parser.error(f"SQLite database was not found: {args.sqlite_path}")

    # Importing the server creates/updates the PostgreSQL schema before copying.
    from webapp import server
    from webapp.db import table_columns

    source = sqlite3.connect(args.sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        with server.db_connection() as target:
            existing = target.execute(
                "SELECT (SELECT COUNT(*) FROM orders) + "
                "(SELECT COUNT(*) FROM categories) + "
                "(SELECT COUNT(*) FROM reviews) AS count"
            ).fetchone()
            if int(existing["count"] or 0):
                raise RuntimeError(
                    "Neon already contains application data. Use a fresh database/branch; "
                    "the importer will not overwrite live data."
                )

        remote_proofs: dict[int, tuple[str, str]] = {}
        proof_rows = source.execute(
            "SELECT id, proof_filename FROM orders "
            "WHERE proof_filename IS NOT NULL AND proof_filename!=''"
        ).fetchall()
        if proof_rows and not server.CLOUDINARY_URL:
            raise RuntimeError("CLOUDINARY_URL is required to migrate existing payment proofs.")
        for proof in proof_rows:
            proof_path = args.sqlite_path.parent / "payment_proofs" / proof["proof_filename"]
            if not proof_path.is_file():
                raise RuntimeError(f"Missing payment proof: {proof_path}")
            url, storage_id = server.store_payment_proof(
                proof_path.read_bytes(), proof["proof_filename"]
            )
            remote_proofs[int(proof["id"])] = (url or "", storage_id or "")

        totals: dict[str, int] = {}
        with server.db_connection() as target:
            for table in TABLES:
                source_cols = sqlite_columns(source, table)
                if not source_cols:
                    totals[table] = 0
                    continue
                target_cols = table_columns(target, table)
                columns = [column for column in source_cols if column in target_cols]
                if table == "orders":
                    columns.extend(
                        column for column in ("proof_url", "proof_storage_id")
                        if column in target_cols and column not in columns
                    )
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
                if table == "settings":
                    rows = [row for row in rows if row["key"] not in {"admin_password", "sync_key"}]
                if not rows:
                    totals[table] = 0
                    continue

                placeholders = ",".join("?" for _ in columns)
                conflict = (
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
                    if table == "settings"
                    else "ON CONFLICT DO NOTHING"
                )
                sql = (
                    f"INSERT INTO {table} ({','.join(columns)}) "
                    f"VALUES ({placeholders}) {conflict}"
                )
                values: list[tuple[Any, ...]] = []
                for row in rows:
                    item: list[Any] = []
                    for column in columns:
                        if column == "proof_url":
                            item.append(remote_proofs.get(int(row["id"]), (None, None))[0])
                        elif column == "proof_storage_id":
                            item.append(remote_proofs.get(int(row["id"]), (None, None))[1])
                        else:
                            item.append(row[column])
                    values.append(tuple(item))
                target.executemany(sql, values)
                totals[table] = len(values)

            for table in SERIAL_TABLES:
                target.execute(
                    "SELECT setval(pg_get_serial_sequence(?, 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                    f"EXISTS(SELECT 1 FROM {table}))",
                    (table,),
                )

        print("Migration completed successfully:")
        for table in TABLES:
            print(f"  {table}: {totals.get(table, 0)}")
        if remote_proofs:
            print(f"  payment proofs uploaded to Cloudinary: {len(remote_proofs)}")
        return 0
    finally:
        source.close()


if __name__ == "__main__":
    raise SystemExit(main())
