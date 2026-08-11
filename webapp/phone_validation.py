"""Shared validation rules for public customer phone numbers."""

from __future__ import annotations

import re


EGYPTIAN_MOBILE_PATTERN = re.compile(r"^01[0125][0-9]{8}$")


def valid_egyptian_mobile(value: str | None) -> bool:
    """Accept only an 11-digit Egyptian mobile number in its local form."""
    return bool(EGYPTIAN_MOBILE_PATTERN.fullmatch((value or "").strip()))
