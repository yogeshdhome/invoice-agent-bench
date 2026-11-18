"""Canonical serialisation, action hashes (approval binding) and idempotency keys."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def _default(o: Any) -> str:
    if isinstance(o, Decimal):
        return format(o.normalize(), "f")
    return str(o)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default, ensure_ascii=True)


def action_hash(tenant_id: str, tool: str, args: dict) -> str:
    """Binds an approval to exactly one action; any argument edit changes the hash (FR-11)."""
    return hashlib.sha256(canonical_json({"t": tenant_id, "tool": tool, "args": args}).encode()).hexdigest()


def idempotency_key(tenant_id: str, tool: str, args: dict, approval_id: str | None = None) -> str:
    raw = canonical_json({"t": tenant_id, "tool": tool, "args": args, "approval": approval_id})
    return "idem-" + hashlib.sha256(raw.encode()).hexdigest()[:40]
