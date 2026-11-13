"""Duplicate detection: exact (normalised vendor invoice number) and near (same total, close dates)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Invoice, InvoiceStatus

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def normalize_vendor_invoice_no(raw: str) -> str:
    s = _NON_ALNUM.sub("", raw.upper())
    if s.startswith("INV"):
        s = s[3:]
    return s.lstrip("0") or "0"


@dataclass(frozen=True)
class DuplicateCandidate:
    invoice_id: str
    kind: str  # EXACT | NEAR

    def as_dict(self) -> dict:
        return {"invoice_id": self.invoice_id, "kind": self.kind}


def find_duplicates(inv: Invoice, others: list[Invoice], window_days: int = 7) -> list[DuplicateCandidate]:
    """Flag `inv` if an EARLIER-received (lower id), non-rejected invoice of the same vendor matches."""
    norm = normalize_vendor_invoice_no(inv.vendor_invoice_no)
    out = []
    for o in others:
        if (o.invoice_id >= inv.invoice_id or o.tenant_id != inv.tenant_id
                or o.vendor_id != inv.vendor_id or o.status == InvoiceStatus.REJECTED):
            continue
        if normalize_vendor_invoice_no(o.vendor_invoice_no) == norm:
            out.append(DuplicateCandidate(o.invoice_id, "EXACT"))
        elif o.total == inv.total and abs((o.invoice_date - inv.invoice_date).days) <= window_days:
            out.append(DuplicateCandidate(o.invoice_id, "NEAR"))
    return sorted(out, key=lambda c: c.invoice_id)
