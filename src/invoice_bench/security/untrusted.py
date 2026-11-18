"""Tagging of vendor-supplied free text as untrusted data (SEC-04)."""
from __future__ import annotations

UNTRUSTED_FIELDS = {"vendor_memo", "attachment_text"}
OPEN, CLOSE = "<untrusted_vendor_text>", "</untrusted_vendor_text>"


def delimit(text: str | None) -> str | None:
    """Wrap untrusted text for the explanation step; strip delimiter look-alikes inside it."""
    if text is None:
        return None
    cleaned = text.replace(OPEN, "").replace(CLOSE, "")
    return f"{OPEN}{cleaned}{CLOSE}"


def strip_untrusted(payload: dict) -> dict:
    """Remove untrusted fields entirely (used for planning context)."""
    return {k: v for k, v in payload.items() if k not in UNTRUSTED_FIELDS}
