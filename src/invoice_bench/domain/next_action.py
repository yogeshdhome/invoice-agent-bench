"""Deterministic next-action table (synthetic AP operating procedure)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import HoldCode, InvoiceStatus, Payment, PaymentStatus


@dataclass(frozen=True)
class NextAction:
    action: str
    owner: str
    description: str

    def as_dict(self) -> dict:
        return {"action": self.action, "owner": self.owner}


HOLD_PRIORITY = [
    HoldCode.PO_NOT_FOUND, HoldCode.PO_CLOSED, HoldCode.PO_EXHAUSTED, HoldCode.CURRENCY_MISMATCH,
    HoldCode.VENDOR_INACTIVE, HoldCode.DUPLICATE_SUSPECT, HoldCode.NO_RECEIPT, HoldCode.QTY_VARIANCE,
    HoldCode.PRICE_VARIANCE,
]

HOLD_ACTIONS: dict[HoldCode, NextAction] = {
    HoldCode.PO_NOT_FOUND: NextAction("PROVIDE_VALID_PO_REFERENCE", "PROCUREMENT_BUYER", "Buyer confirms the correct PO; AP updates the PO reference (approval required)."),
    HoldCode.PO_CLOSED: NextAction("REOPEN_PO_OR_REJECT_INVOICE", "PROCUREMENT_BUYER", "Buyer reopens/extends the PO or AP rejects the invoice."),
    HoldCode.PO_EXHAUSTED: NextAction("INCREASE_PO_VALUE_OR_REJECT", "PROCUREMENT_BUYER", "Buyer raises a PO change for additional value or AP rejects the excess."),
    HoldCode.CURRENCY_MISMATCH: NextAction("REQUEST_CORRECTED_INVOICE", "AP_CLERK", "Ask the vendor for an invoice in the PO currency."),
    HoldCode.VENDOR_INACTIVE: NextAction("VENDOR_MASTER_REVIEW", "VENDOR_MASTER_TEAM", "Vendor master team reviews/reactivates the vendor; AP cannot pay inactive vendors."),
    HoldCode.DUPLICATE_SUSPECT: NextAction("REVIEW_AND_REJECT_DUPLICATE", "AP_SUPERVISOR", "Compare with the earlier invoice; reject if duplicate (approval required)."),
    HoldCode.NO_RECEIPT: NextAction("POST_GOODS_RECEIPT", "RECEIVING", "Receiving posts the goods receipt; the hold re-evaluates on the next match run."),
    HoldCode.QTY_VARIANCE: NextAction("CONFIRM_RECEIPT_OR_REQUEST_CREDIT", "AP_CLERK", "Confirm remaining receipts or request a credit memo for the excess quantity."),
    HoldCode.PRICE_VARIANCE: NextAction("REQUEST_PO_PRICE_AMENDMENT_OR_CREDIT_MEMO", "PROCUREMENT_BUYER", "Buyer amends the PO price or AP requests a credit memo from the vendor."),
}

STATUS_ACTIONS: dict[InvoiceStatus, NextAction] = {
    InvoiceStatus.RECEIVED: NextAction("AWAIT_MATCHING", "AP_CLERK", "Invoice is awaiting the next automated match run."),
    InvoiceStatus.APPROVED: NextAction("AWAIT_PAYMENT_RUN", "FINANCE_CONTROLLER", "Approved; will be picked up by the next payment run."),
    InvoiceStatus.SCHEDULED: NextAction("NONE_PAYMENT_SCHEDULED", "NONE", "Payment is scheduled; no action needed."),
    InvoiceStatus.PAID: NextAction("NONE_PAID", "NONE", "Invoice is paid; no action needed."),
    InvoiceStatus.PARTIALLY_PAID: NextAction("FOLLOW_UP_REMAINING_BALANCE", "AP_CLERK", "Investigate why the remaining balance was not paid."),
    InvoiceStatus.REJECTED: NextAction("NONE_REJECTED", "NONE", "Invoice was rejected; vendor may dispute via AP."),
}

PAYMENT_FAILED_ACTION = NextAction("VENDOR_MASTER_VERIFY_BANK_DETAILS", "VENDOR_MASTER_TEAM",
                                   "Payment failed; vendor master team verifies bank details through the vendor verification process.")


def recommend(status: InvoiceStatus, hold_codes: list[HoldCode], payments: list[Payment] | None = None) -> list[NextAction]:
    if hold_codes:
        return [HOLD_ACTIONS[c] for c in HOLD_PRIORITY if c in set(hold_codes)]
    if payments and any(p.status == PaymentStatus.FAILED for p in payments) and status != InvoiceStatus.PAID:
        return [PAYMENT_FAILED_ACTION]
    return [STATUS_ACTIONS[status]] if status in STATUS_ACTIONS else []
