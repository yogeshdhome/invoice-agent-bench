from datetime import date
from decimal import Decimal as D

from invoice_bench.domain.models import (GoodsReceipt, GRLine, HoldCode, Invoice, InvoiceLine, POLine, PurchaseOrder,
                                         Vendor)
from invoice_bench.domain.next_action import recommend
from invoice_bench.domain.rules import Tolerance, evaluate_invoice


def po(price="100.00", qty=10, status="OPEN", currency="USD", consumed="0", total=None):
    line = POLine(po_line_id="L1", po_id="PO-00001", line_no=1, sku="S1", qty=qty, unit_price=D(price))
    return PurchaseOrder(po_id="PO-00001", tenant_id="t", bu_id="b", vendor_id="V-1", status=status, currency=currency,
                         total_amount=D(total or str(D(price) * qty)), consumed_amount=D(consumed), created_at=date(2026, 9, 1),
                         lines=(line,))


def gr(qty):
    return [GoodsReceipt(gr_id="GR-1", po_id="PO-00001", received_at=date(2026, 10, 1),
                         lines=(GRLine(gr_line_id="G1", gr_id="GR-1", po_line_id="L1", qty_received=qty),))] if qty else []


def inv(price="100.00", qty=10, currency="USD", iid="INV-00002", vin="VI-1", d=date(2026, 10, 20), po_ref="PO-00001"):
    amt = D(price) * qty
    return Invoice(invoice_id=iid, tenant_id="t", bu_id="b", vendor_id="V-1", po_ref=po_ref, vendor_invoice_no=vin,
                   invoice_date=d, currency=currency, subtotal=amt, tax=D(0), total=amt, status="ON_HOLD",
                   lines=(InvoiceLine(invoice_line_id="IL1", invoice_id=iid, po_line_id="L1", sku="S1", qty=qty,
                                      unit_price=D(price), amount=amt),))


VENDOR = Vendor(vendor_id="V-1", tenant_id="t", name="v", status="ACTIVE", bank_account="SYNBANK-1")


def codes(i, p, receipts, vendor=VENDOR, others=()):
    return evaluate_invoice(i, p, receipts, vendor, list(others), Tolerance()).codes


def test_clean_match():
    assert codes(inv(), po(), gr(10)) == []


def test_price_boundary_exactly_2pct_passes():
    assert codes(inv("102.00", 5), po("100.00", 5), gr(5)) == []


def test_price_boundary_2_01pct_fails():
    assert codes(inv("102.01", 5), po("100.00", 5), gr(5)) == [HoldCode.PRICE_VARIANCE]


def test_amount_cap_fails_even_under_pct():
    assert codes(inv("406.00", 10), po("400.00", 10), gr(10)) == [HoldCode.PRICE_VARIANCE]


def test_underbilling_never_a_variance():
    assert codes(inv("80.00", 10), po("100.00", 10), gr(10)) == []


def test_no_receipt_and_qty_variance():
    assert codes(inv(), po(), gr(0)) == [HoldCode.NO_RECEIPT]
    assert codes(inv(qty=10), po(qty=10), gr(7)) == [HoldCode.QTY_VARIANCE]


def test_po_not_found_closed_exhausted_currency():
    assert codes(inv(po_ref=None), None, []) == [HoldCode.PO_NOT_FOUND]
    assert codes(inv(), po(status="CLOSED"), gr(10)) == [HoldCode.PO_CLOSED]
    assert codes(inv(), po(consumed="950.00"), gr(10)) == [HoldCode.PO_EXHAUSTED]
    assert codes(inv(currency="EUR"), po(), gr(10)) == [HoldCode.CURRENCY_MISMATCH]  # price checks skipped across currencies


def test_overrun_tolerance_is_10pct():
    assert codes(inv(), po(consumed="100.00"), gr(10)) == []        # 1100 <= 1100
    assert codes(inv(), po(consumed="100.01"), gr(10)) == [HoldCode.PO_EXHAUSTED]


def test_vendor_inactive():
    v = VENDOR.model_copy(update={"status": "INACTIVE"})
    assert codes(inv(), po(), gr(10), vendor=v) == [HoldCode.VENDOR_INACTIVE]


def test_next_action_priority_and_payment_failed():
    acts = recommend("ON_HOLD", [HoldCode.PRICE_VARIANCE, HoldCode.PO_CLOSED])
    assert [a.action for a in acts][0] == "REOPEN_PO_OR_REJECT_INVOICE"
    assert recommend("APPROVED", [])[0].action == "AWAIT_PAYMENT_RUN"
