"""Build-time connection defaults for a new POS installation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


FALLBACK_SERVER_URL = "https://broost-production-1dcb.up.railway.app"
LEGACY_SERVER_URLS = {"https://broost-production-4411.up.railway.app"}
FALLBACK_SYNC_KEY = "broost-local-sync"


def normalize_server_url(value: str) -> str:
    url = str(value).strip().rstrip("/")
    return FALLBACK_SERVER_URL if url.lower() in LEGACY_SERVER_URLS else url


def _candidate_files() -> list[Path]:
    if getattr(sys, "frozen", False):
        resource_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return [resource_root / "pos_defaults.json", Path(sys.executable).resolve().parent / "pos_defaults.json"]
    root = Path(__file__).resolve().parent.parent
    return [root / "pos_defaults.json", root / "build" / "pos_defaults.json"]


def load_pos_defaults() -> dict[str, str]:
    payload: dict[str, Any] = {}
    for path in _candidate_files():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
                continue
            break
        except (OSError, ValueError, TypeError):
            continue
    return {
        "server_url": normalize_server_url(os.getenv("BROOST_POS_SERVER_URL") or payload.get("server_url") or FALLBACK_SERVER_URL),
        "sync_key": str(os.getenv("BROOST_SYNC_KEY") or payload.get("sync_key") or FALLBACK_SYNC_KEY).strip(),
        "operational_reset_id": str(os.getenv("BROOST_OPERATIONAL_RESET_ID") or payload.get("operational_reset_id") or '').strip(),
    }
