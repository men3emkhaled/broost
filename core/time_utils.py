# -*- coding: utf-8 -*-
"""Time conversion helpers shared by website synchronization and the POS UI."""

from datetime import datetime, timezone


DB_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_iso_timestamp(value: str) -> datetime:
    text = str(value).strip()
    if text.upper().endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def to_local_db_timestamp(value: str | None) -> str | None:
    """Convert an ISO timestamp with a timezone to local time; keep naive local values local."""
    if not value:
        return None
    try:
        parsed = _parse_iso_timestamp(value)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.replace(tzinfo=None).strftime(DB_TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return str(value).replace("T", " ").replace("Z", "")[:19]


def legacy_utc_to_local_db_timestamp(value: str | None) -> str | None:
    """Repair old online timestamps whose UTC marker was previously stripped."""
    if not value:
        return None
    try:
        parsed = _parse_iso_timestamp(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().replace(tzinfo=None).strftime(DB_TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return value


def elapsed_minutes(value: str | None, now: datetime | None = None) -> int:
    """Return a safe, non-negative number of elapsed local minutes."""
    if not value:
        return 0
    try:
        created = datetime.strptime(str(value)[:19], DB_TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return 0
    current = now or datetime.now()
    return max(0, int((current - created).total_seconds() / 60))
