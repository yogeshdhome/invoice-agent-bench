"""Masking of bank / tax identifiers before data leaves the service boundary (SEC-09)."""
from __future__ import annotations

import re

_BANK = re.compile(r"SYNBANK-[A-Z0-9-]+")


def mask_account(value: str | None) -> str | None:
    if not value:
        return value
    tail = re.sub(r"[^A-Z0-9]", "", value.upper())[-4:]
    return "****" + tail


def mask_text(text: str | None) -> str | None:
    if not text:
        return text
    return _BANK.sub(lambda m: mask_account(m.group(0)) or "", text)
