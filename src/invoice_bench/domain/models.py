"""Domain models for the synthetic AP world. Amounts are Decimal; dates are ISO dates."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    AP_CLERK = "AP_CLERK"
    AP_SUPERVISOR = "AP_SUPERVISOR"
    PROCUREMENT_BUYER = "PROCUREMENT_BUYER"
    FINANCE_CONTROLLER = "FINANCE_CONTROLLER"
    AUDITOR_READONLY = "AUDITOR_READONLY"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"


class InvoiceStatus(StrEnum):
    RECEIVED = "RECEIVED"
    ON_HOLD = "ON_HOLD"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    REJECTED = "REJECTED"


PRE_PAYMENT_STATUSES = {InvoiceStatus.RECEIVED, InvoiceStatus.ON_HOLD, InvoiceStatus.APPROVED}


class HoldCode(StrEnum):
    PO_NOT_FOUND = "PO_NOT_FOUND"
    PO_CLOSED = "PO_CLOSED"
    PO_EXHAUSTED = "PO_EXHAUSTED"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    VENDOR_INACTIVE = "VENDOR_INACTIVE"
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT"
    NO_RECEIPT = "NO_RECEIPT"
    QTY_VARIANCE = "QTY_VARIANCE"
    PRICE_VARIANCE = "PRICE_VARIANCE"


class POStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class VendorStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"


class PaymentStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    PAID = "PAID"
    FAILED = "FAILED"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Vendor(_Frozen):
    vendor_id: str
    tenant_id: str
    name: str
    status: VendorStatus
    bank_account: str  # masked by services before leaving the service boundary
    bank_changed_at: date | None = None


class POLine(_Frozen):
    po_line_id: str
    po_id: str
    line_no: int
    sku: str
    qty: int
    unit_price: Decimal


class PurchaseOrder(_Frozen):
    po_id: str
    tenant_id: str
    bu_id: str
    vendor_id: str
    status: POStatus
    currency: str
    total_amount: Decimal
    consumed_amount: Decimal
    created_at: date
    lines: tuple[POLine, ...] = ()


class GRLine(_Frozen):
    gr_line_id: str
    gr_id: str
    po_line_id: str
    qty_received: int


class GoodsReceipt(_Frozen):
    gr_id: str
    po_id: str
    received_at: date
    lines: tuple[GRLine, ...] = ()


class InvoiceLine(_Frozen):
    invoice_line_id: str
    invoice_id: str
    po_line_id: str | None
    sku: str
    qty: int
    unit_price: Decimal
    amount: Decimal


class Hold(_Frozen):
    hold_id: str
    invoice_id: str
    code: HoldCode
    created_at: date
    released_at: date | None = None
    released_by: str | None = None
    reason: str | None = None


class Invoice(_Frozen):
    invoice_id: str
    tenant_id: str
    bu_id: str
    vendor_id: str
    po_ref: str | None  # PO number as supplied by the vendor; may not resolve
    vendor_invoice_no: str
    invoice_date: date
    currency: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: InvoiceStatus
    status_reason: str | None = None
    vendor_memo: str | None = None       # UNTRUSTED (vendor-supplied)
    attachment_text: str | None = None   # UNTRUSTED (vendor-supplied)
    lines: tuple[InvoiceLine, ...] = ()
    holds: tuple[Hold, ...] = ()         # active holds only

    @property
    def active_hold_codes(self) -> list[HoldCode]:
        return sorted({h.code for h in self.holds if h.released_at is None})


class Payment(_Frozen):
    payment_id: str
    invoice_id: str
    amount: Decimal
    status: PaymentStatus
    scheduled_date: date | None = None
    paid_date: date | None = None
    failure_reason: str | None = None
