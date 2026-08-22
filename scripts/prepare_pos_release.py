"""Generate the small POS-only defaults payload used by Windows builds."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from dotenv import dotenv_values


DEFAULT_SERVER_URL = "https://broost-production-4411.up.railway.app"


def load_values(root: Path) -> dict[str, str]:
    env_file = dotenv_values(root / ".env") if (root / ".env").exists() else {}
    server_url = str(os.getenv("BROOST_POS_SERVER_URL") or env_file.get("BROOST_POS_SERVER_URL") or DEFAULT_SERVER_URL).strip().rstrip("/")
    sync_key = str(os.getenv("BROOST_SYNC_KEY") or env_file.get("BROOST_SYNC_KEY") or "").strip()
    if not sync_key:
        raise SystemExit("BROOST_SYNC_KEY is required in .env when building the POS installer")
    return {"server_url": server_url, "sync_key": sync_key}


def write_defaults(output: Path, values: dict[str, str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_database(database_path: Path, values: dict[str, str]) -> None:
    if not database_path.exists():
        return
    conn = sqlite3.connect(database_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        settings = {
            "web_server_url": values["server_url"],
            "web_sync_key": values["sync_key"],
            "web_sync_enabled": "1",
            "web_sync_epoch": "",
            "web_last_event_id": "0",
            "web_menu_version": "0",
            "web_menu_fingerprint": "",
            "web_initial_orders_synced": "0",
        }
        conn.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            settings.items(),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    values = load_values(root)
    write_defaults(args.output, values)
    if args.database:
        prepare_database(args.database, values)
    print("POS release defaults prepared (sync key hidden).")


if __name__ == "__main__":
    main()
