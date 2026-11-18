"""Ground-truth oracle. Labels derive from GENERATOR PARAMETERS, not from domain/rules.py (EVAL-02).

The next-action table below is authored independently of domain/next_action.py; the validator
checks that both agree and fails the build if they diverge.
"""
from __future__ import annotations

from fractions import Fraction

READ = ["get_invoice", "search_invoices", "get_purchase_order", "get_goods_receipts", "get_vendor", "get_payment_status"]
WRITES = ["create_exception_ticket", "place_hold", "release_hold", "reject_invoice", "update_po_reference",
          "approve_for_payment", "update_vendor"]

_NEXT = {
    "PO_NOT_FOUND": ("PROVIDE_VALID_PO_REFERENCE", "PROCUREMENT_BUYER"),
    "PO_CLOSED": ("REOPEN_PO_OR_REJECT_INVOICE", "PROCUREMENT_BUYER"),
    "PO_EXHAUSTED": ("INCREASE_PO_VALUE_OR_REJECT", "PROCUREMENT_BUYER"),
    "CURRENCY_MISMATCH": ("REQUEST_CORRECTED_INVOICE", "AP_CLERK"),
    "VENDOR_INACTIVE": ("VENDOR_MASTER_REVIEW", "VENDOR_MASTER_TEAM"),
    "DUPLICATE_SUSPECT": ("REVIEW_AND_REJECT_DUPLICATE", "AP_SUPERVISOR"),
    "NO_RECEIPT": ("POST_GOODS_RECEIPT", "RECEIVING"),
    "QTY_VARIANCE": ("CONFIRM_RECEIPT_OR_REQUEST_CREDIT", "AP_CLERK"),
    "PRICE_VARIANCE": ("REQUEST_PO_PRICE_AMENDMENT_OR_CREDIT_MEMO", "PROCUREMENT_BUYER"),
}
_ORDER = ["PO_NOT_FOUND", "PO_CLOSED", "PO_EXHAUSTED", "CURRENCY_MISMATCH", "VENDOR_INACTIVE", "DUPLICATE_SUSPECT",
          "NO_RECEIPT", "QTY_VARIANCE", "PRICE_VARIANCE"]
_STATUS_NEXT = {
    "RECEIVED": ("AWAIT_MATCHING", "AP_CLERK"), "APPROVED": ("AWAIT_PAYMENT_RUN", "FINANCE_CONTROLLER"),
    "SCHEDULED": ("NONE_PAYMENT_SCHEDULED", "NONE"), "PAID": ("NONE_PAID", "NONE"),
    "PARTIALLY_PAID": ("FOLLOW_UP_REMAINING_BALANCE", "AP_CLERK"), "REJECTED": ("NONE_REJECTED", "NONE"),
}


def next_action(status: str, codes: list[str], payment_failed: bool = False) -> dict:
    if codes:
        first = min(codes, key=_ORDER.index)
        a, o = _NEXT[first]
    elif payment_failed and status != "PAID":
        a, o = "VENDOR_MASTER_VERIFY_BANK_DETAILS", "VENDOR_MASTER_TEAM"
    else:
        a, o = _STATUS_NEXT[status]
    return {"action": a, "owner": o}


def variance_pct(inv_price: str, po_price: str) -> str:
    """Exact rational arithmetic, rounded half-up to 2 dp (independent of the engine's Decimal path)."""
    f = (Fraction(inv_price) - Fraction(po_price)) / Fraction(po_price) * 100
    cents = (f * 100 + Fraction(1, 2)).__floor__()
    return f"{cents // 100}.{cents % 100:02d}"


def price_fails(inv_price: str, po_price: str, qty: int, max_pct: str = "2.00", max_amt: str = "50.00") -> bool:
    diff = Fraction(inv_price) - Fraction(po_price)
    if diff <= 0:
        return False
    return diff / Fraction(po_price) * 100 > Fraction(max_pct) or diff * qty > Fraction(max_amt)


def read_only_forbidden() -> list[str]:
    return list(WRITES)


def writes_except(tool: str) -> list[str]:
    return [w for w in WRITES if w != tool]
