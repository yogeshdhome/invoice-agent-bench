"""Deterministic 3-way-match rule engine. Pure functions, no I/O.

Used by the HARDENED agent. Ground truth comes from data/oracle.py, which deliberately
shares no logic with this file (EVAL-02).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

from .duplicates import find_duplicates
from .models import GoodsReceipt, HoldCode, Invoice, POStatus, PurchaseOrder, Vendor, VendorStatus

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class Tolerance:
    max_price_variance_pct: Decimal = Decimal("2.00")
    max_price_variance_amount: Decimal = Decimal("50.00")
    po_overrun_pct: Decimal = Decimal("10.00")
    duplicate_window_days: int = 7

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Tolerance":
        d = yaml.safe_load(Path(path).read_text())
        return cls(Decimal(d["max_price_variance_pct"]), Decimal(d["max_price_variance_amount"]),
                   Decimal(d["po_overrun_pct"]), int(d["duplicate_window_days"]))


@dataclass(frozen=True)
class Finding:
    code: HoldCode
    rule_id: str
    message: str
    evidence: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Evaluation:
    invoice_id: str
    findings: tuple[Finding, ...]

    @property
    def codes(self) -> list[HoldCode]:
        return sorted({f.code for f in self.findings})


def _pct(diff: Decimal, base: Decimal) -> Decimal:
    return (diff / base * HUNDRED).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def check_po(inv: Invoice, po: PurchaseOrder | None, tol: Tolerance) -> list[Finding]:
    if po is None or po.tenant_id != inv.tenant_id:
        return [Finding(HoldCode.PO_NOT_FOUND, "R-PO-01", "Referenced PO not found", {"po_ref": inv.po_ref})]
    out: list[Finding] = []
    if po.status in (POStatus.CLOSED, POStatus.CANCELLED):
        out.append(Finding(HoldCode.PO_CLOSED, "R-PO-02", f"PO is {po.status}", {"po_id": po.po_id, "po_status": str(po.status)}))
    else:
        limit = po.total_amount * (1 + tol.po_overrun_pct / HUNDRED)
        if po.consumed_amount + inv.subtotal > limit:
            out.append(Finding(HoldCode.PO_EXHAUSTED, "R-PO-03", "Invoice exceeds remaining PO value",
                               {"po_total": str(po.total_amount), "consumed": str(po.consumed_amount),
                                "invoice_subtotal": str(inv.subtotal)}))
    if inv.currency != po.currency:
        out.append(Finding(HoldCode.CURRENCY_MISMATCH, "R-PO-04", "Invoice currency differs from PO",
                           {"invoice_currency": inv.currency, "po_currency": po.currency}))
    return out


def check_lines(inv: Invoice, po: PurchaseOrder, receipts: list[GoodsReceipt], tol: Tolerance) -> list[Finding]:
    """Price and quantity checks. Simplification: prior invoiced quantity is not netted (documented)."""
    if inv.currency != po.currency:
        return []  # price comparison is meaningless across currencies
    po_lines = {pl.po_line_id: pl for pl in po.lines}
    received: dict[str, int] = {}
    for gr in receipts:
        for gl in gr.lines:
            received[gl.po_line_id] = received.get(gl.po_line_id, 0) + gl.qty_received
    price_ev, qty_ev, no_rcpt_ev = [], [], []
    for line in inv.lines:
        pl = po_lines.get(line.po_line_id or "")
        if pl is None:
            continue
        diff = line.unit_price - pl.unit_price
        if diff > 0:
            pct = _pct(diff, pl.unit_price)
            amount = diff * line.qty
            if pct > tol.max_price_variance_pct or amount > tol.max_price_variance_amount:
                price_ev.append({"po_line_id": pl.po_line_id, "invoice_unit_price": str(line.unit_price),
                                 "po_unit_price": str(pl.unit_price), "variance_pct": str(pct.quantize(Decimal("0.01"))),
                                 "variance_amount": str(amount)})
        rec = received.get(pl.po_line_id, 0)
        if rec == 0:
            no_rcpt_ev.append({"po_line_id": pl.po_line_id})
        elif line.qty > rec:
            qty_ev.append({"po_line_id": pl.po_line_id, "invoiced_qty": line.qty, "received_qty": rec})
    out = []
    if price_ev:
        out.append(Finding(HoldCode.PRICE_VARIANCE, "R-LN-01", "Unit price exceeds PO beyond tolerance", {"lines": price_ev}))
    if no_rcpt_ev:
        out.append(Finding(HoldCode.NO_RECEIPT, "R-LN-02", "No goods receipt for invoiced line(s)", {"lines": no_rcpt_ev}))
    if qty_ev:
        out.append(Finding(HoldCode.QTY_VARIANCE, "R-LN-03", "Invoiced quantity exceeds received quantity", {"lines": qty_ev}))
    return out


def check_vendor(inv: Invoice, vendor: Vendor | None) -> list[Finding]:
    if vendor is not None and vendor.status != VendorStatus.ACTIVE:
        return [Finding(HoldCode.VENDOR_INACTIVE, "R-VD-01", f"Vendor is {vendor.status}", {"vendor_id": vendor.vendor_id})]
    return []


def evaluate_invoice(inv: Invoice, po: PurchaseOrder | None, receipts: list[GoodsReceipt], vendor: Vendor | None,
                     same_vendor_invoices: list[Invoice], tol: Tolerance | None = None) -> Evaluation:
    tol = tol or Tolerance()
    findings = check_po(inv, po, tol)
    if po is not None and po.tenant_id == inv.tenant_id:
        findings += check_lines(inv, po, receipts, tol)
    findings += check_vendor(inv, vendor)
    dups = find_duplicates(inv, same_vendor_invoices, tol.duplicate_window_days)
    if dups:
        findings.append(Finding(HoldCode.DUPLICATE_SUSPECT, "R-DP-01", "Possible duplicate invoice",
                                {"candidates": [d.as_dict() for d in dups]}))
    return Evaluation(inv.invoice_id, tuple(sorted(findings, key=lambda f: f.code)))
