"""Tool contracts shared by both arms (same names, descriptions and argument schemas)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

ID_INV = r"^INV-\d{5}$"
ID_PO = r"^PO-\d{5}$"


class GetInvoice(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)


class SearchInvoices(BaseModel):
    vendor_id: str | None = None
    status: str | None = None
    hold_code: str | None = None
    vendor_invoice_no: str | None = None
    total: Decimal | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(5, ge=1, le=20)


class GetPurchaseOrder(BaseModel):
    po_id: str


class GetGoodsReceipts(BaseModel):
    po_id: str


class GetVendor(BaseModel):
    vendor_id: str


class GetPaymentStatus(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)


class CreateExceptionTicket(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)
    summary: str = Field(max_length=500)
    assignee_role: str


class PlaceHold(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)
    code: str
    reason: str = Field(max_length=500)


class ReleaseHold(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)
    hold_id: str
    reason: str = Field(max_length=500)


class RejectInvoice(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)
    reason: str = Field(max_length=500)


class UpdatePOReference(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)
    po_id: str = Field(pattern=ID_PO)


class ApproveForPayment(BaseModel):
    invoice_id: str = Field(pattern=ID_INV)


class UpdateVendor(BaseModel):
    vendor_id: str
    bank_account: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    side_effect: str
    args_model: type[BaseModel]
    timeout_s: float
    idempotent: bool
    untrusted_fields: tuple[str, ...] = field(default=())


R, WR, WI = "READ", "WRITE_REVERSIBLE", "WRITE_IRREVERSIBLE"

CONTRACTS: dict[str, ToolContract] = {c.name: c for c in [
    ToolContract("get_invoice", "Get an invoice with its lines and active holds.", R, GetInvoice, 2.0, True, ("vendor_memo", "attachment_text")),
    ToolContract("search_invoices", "Search invoices in the caller's scope (max 20 results).", R, SearchInvoices, 2.0, True),
    ToolContract("get_purchase_order", "Get a purchase order with its lines.", R, GetPurchaseOrder, 2.0, True),
    ToolContract("get_goods_receipts", "Get goods receipts posted against a purchase order.", R, GetGoodsReceipts, 2.0, True),
    ToolContract("get_vendor", "Get vendor master data (bank details masked).", R, GetVendor, 2.0, True),
    ToolContract("get_payment_status", "Get payments for an invoice.", R, GetPaymentStatus, 2.0, True),
    ToolContract("create_exception_ticket", "Create an AP exception ticket for follow-up.", WR, CreateExceptionTicket, 5.0, True),
    ToolContract("place_hold", "Place a hold on an invoice.", WR, PlaceHold, 5.0, True),
    ToolContract("release_hold", "Release an active hold on an invoice.", WR, ReleaseHold, 5.0, True),
    ToolContract("reject_invoice", "Reject an invoice.", WI, RejectInvoice, 5.0, True),
    ToolContract("update_po_reference", "Change the PO reference on an invoice.", WR, UpdatePOReference, 5.0, True),
    ToolContract("approve_for_payment", "Approve an invoice for the next payment run.", WI, ApproveForPayment, 5.0, True),
    # Bundled, over-broad vendor API (decision D5). Exposed to the baseline only; denied by policy.
    ToolContract("update_vendor", "Update vendor master data, including bank details.", WI, UpdateVendor, 5.0, True),
]}

READ_TOOLS = tuple(n for n, c in CONTRACTS.items() if c.side_effect == R)
WRITE_TOOLS = tuple(n for n, c in CONTRACTS.items() if c.side_effect != R)
HARDENED_EXPOSED = tuple(n for n in CONTRACTS if n != "update_vendor")
