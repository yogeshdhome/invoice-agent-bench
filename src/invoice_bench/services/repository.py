"""Data access with ERP-style data scoping.

User (on-behalf-of) principals see only their tenant and BUs. The SERVICE_ACCOUNT principal sees
everything — that is the confused-deputy credential the baseline uses (decision D4).
Role/approval policy is NOT enforced here; that is the policy engine's job.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal

from ..domain.models import (GoodsReceipt, GRLine, Hold, HoldCode, Invoice, InvoiceLine, InvoiceStatus, Payment,
                             POLine, PurchaseOrder, Vendor)
from ..security.auth import Principal

ALL_BU_ROLES = {"AP_SUPERVISOR", "FINANCE_CONTROLLER", "AUDITOR_READONLY"}


class NotFound(Exception):
    pass


class PreconditionFailed(Exception):
    pass


def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


class Repo:
    def __init__(self, conn: sqlite3.Connection, principal: Principal):
        self.c = conn
        self.p = principal

    # ---- scoping -------------------------------------------------------------------------------
    def _scope(self, alias: str, bu: bool = True) -> tuple[str, list]:
        if self.p.is_service_account:
            return "1=1", []
        clause, params = f"{alias}.tenant_id = ?", [self.p.tenant_id]
        if bu and not (set(map(str, self.p.roles)) & ALL_BU_ROLES):
            if not self.p.bu_ids:
                return "1=0", []
            clause += f" AND {alias}.bu_id IN ({','.join('?' * len(self.p.bu_ids))})"
            params += list(self.p.bu_ids)
        return clause, params

    # ---- reads ---------------------------------------------------------------------------------
    def get_invoice(self, invoice_id: str) -> Invoice:
        sc, ps = self._scope("i")
        r = self.c.execute(f"SELECT * FROM invoices i WHERE i.invoice_id=? AND {sc}", [invoice_id, *ps]).fetchone()
        if r is None:
            raise NotFound(invoice_id)
        return self._invoice(r)

    def _invoice(self, r: sqlite3.Row) -> Invoice:
        lines = tuple(InvoiceLine(invoice_line_id=l["invoice_line_id"], invoice_id=l["invoice_id"], po_line_id=l["po_line_id"],
                                  sku=l["sku"], qty=l["qty"], unit_price=Decimal(l["unit_price"]), amount=Decimal(l["amount"]))
                      for l in self.c.execute("SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY invoice_line_id", [r["invoice_id"]]))
        holds = tuple(Hold(hold_id=h["hold_id"], invoice_id=h["invoice_id"], code=HoldCode(h["code"]), created_at=_d(h["created_at"]),
                           released_at=None, released_by=None, reason=h["reason"])
                      for h in self.c.execute("SELECT * FROM holds WHERE invoice_id=? AND released_at IS NULL ORDER BY hold_id",
                                              [r["invoice_id"]]))
        return Invoice(invoice_id=r["invoice_id"], tenant_id=r["tenant_id"], bu_id=r["bu_id"], vendor_id=r["vendor_id"],
                       po_ref=r["po_ref"], vendor_invoice_no=r["vendor_invoice_no"], invoice_date=_d(r["invoice_date"]),
                       currency=r["currency"], subtotal=Decimal(r["subtotal"]), tax=Decimal(r["tax"]), total=Decimal(r["total"]),
                       status=InvoiceStatus(r["status"]), status_reason=r["status_reason"], vendor_memo=r["vendor_memo"],
                       attachment_text=r["attachment_text"], lines=lines, holds=holds)

    def search_invoices(self, vendor_id=None, status=None, hold_code=None, vendor_invoice_no=None, total=None,
                        date_from=None, date_to=None, limit: int = 5) -> list[dict]:
        sc, ps = self._scope("i")
        q, params = [sc], list(ps)
        for col, val in (("i.vendor_id", vendor_id), ("i.status", status), ("i.vendor_invoice_no", vendor_invoice_no),
                         ("i.total", None if total is None else str(Decimal(str(total))))):
            if val is not None:
                q.append(f"{col} = ?")
                params.append(val)
        if date_from:
            q.append("i.invoice_date >= ?"); params.append(str(date_from))
        if date_to:
            q.append("i.invoice_date <= ?"); params.append(str(date_to))
        if hold_code:
            q.append("EXISTS (SELECT 1 FROM holds h WHERE h.invoice_id=i.invoice_id AND h.released_at IS NULL AND h.code=?)")
            params.append(hold_code)
        limit = max(1, min(int(limit), 20))
        rows = self.c.execute(f"SELECT i.* FROM invoices i WHERE {' AND '.join(q)} ORDER BY i.invoice_id LIMIT ?",
                              [*params, limit + 1]).fetchall()
        out = [{"invoice_id": r["invoice_id"], "vendor_id": r["vendor_id"], "vendor_invoice_no": r["vendor_invoice_no"],
                "invoice_date": r["invoice_date"], "currency": r["currency"], "total": r["total"], "status": r["status"],
                "bu_id": r["bu_id"]} for r in rows[:limit]]
        return out + ([{"truncated": True}] if len(rows) > limit else [])

    def get_po(self, po_id: str) -> PurchaseOrder:
        sc, ps = self._scope("p")
        r = self.c.execute(f"SELECT * FROM purchase_orders p WHERE p.po_id=? AND {sc}", [po_id, *ps]).fetchone()
        if r is None:
            raise NotFound(po_id)
        lines = tuple(POLine(po_line_id=l["po_line_id"], po_id=l["po_id"], line_no=l["line_no"], sku=l["sku"], qty=l["qty"],
                             unit_price=Decimal(l["unit_price"]))
                      for l in self.c.execute("SELECT * FROM po_lines WHERE po_id=? ORDER BY line_no", [po_id]))
        return PurchaseOrder(po_id=r["po_id"], tenant_id=r["tenant_id"], bu_id=r["bu_id"], vendor_id=r["vendor_id"],
                             status=r["status"], currency=r["currency"], total_amount=Decimal(r["total_amount"]),
                             consumed_amount=Decimal(r["consumed_amount"]), created_at=_d(r["created_at"]), lines=lines)

    def get_receipts(self, po_id: str) -> list[GoodsReceipt]:
        self.get_po(po_id)  # scope check
        out = []
        for g in self.c.execute("SELECT * FROM goods_receipts WHERE po_id=? ORDER BY gr_id", [po_id]):
            lines = tuple(GRLine(gr_line_id=x["gr_line_id"], gr_id=x["gr_id"], po_line_id=x["po_line_id"], qty_received=x["qty_received"])
                          for x in self.c.execute("SELECT * FROM gr_lines WHERE gr_id=? ORDER BY gr_line_id", [g["gr_id"]]))
            out.append(GoodsReceipt(gr_id=g["gr_id"], po_id=po_id, received_at=_d(g["received_at"]), lines=lines))
        return out

    def get_vendor(self, vendor_id: str) -> Vendor:
        sc, ps = self._scope("v", bu=False)
        r = self.c.execute(f"SELECT * FROM vendors v WHERE v.vendor_id=? AND {sc}", [vendor_id, *ps]).fetchone()
        if r is None:
            raise NotFound(vendor_id)
        return Vendor(vendor_id=r["vendor_id"], tenant_id=r["tenant_id"], name=r["name"], status=r["status"],
                      bank_account=r["bank_account"], bank_changed_at=_d(r["bank_changed_at"]))

    def get_payments(self, invoice_id: str) -> list[Payment]:
        self.get_invoice(invoice_id)
        return [Payment(payment_id=r["payment_id"], invoice_id=r["invoice_id"], amount=Decimal(r["amount"]), status=r["status"],
                        scheduled_date=_d(r["scheduled_date"]), paid_date=_d(r["paid_date"]), failure_reason=r["failure_reason"])
                for r in self.c.execute("SELECT * FROM payments WHERE invoice_id=? ORDER BY payment_id", [invoice_id])]

    def vendor_invoices(self, tenant_id: str, vendor_id: str) -> list[Invoice]:
        """Unscoped helper for validation and the hardened rule engine's duplicate check (tenant-bounded)."""
        return [self._invoice(r) for r in self.c.execute(
            "SELECT * FROM invoices WHERE tenant_id=? AND vendor_id=? ORDER BY invoice_id", [tenant_id, vendor_id])]

    # ---- writes (caller wraps in a transaction + idempotency) -----------------------------------
    def _next_id(self, table: str, col: str, prefix: str) -> str:
        n = self.c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] + 1
        while True:
            cand = f"{prefix}{n:05d}"
            if self.c.execute(f"SELECT 1 FROM {table} WHERE {col}=?", [cand]).fetchone() is None:
                return cand
            n += 1

    def place_hold(self, invoice_id: str, code: str, reason: str, today: str) -> dict:
        inv = self.get_invoice(invoice_id)
        HoldCode(code)
        hid = self._next_id("holds", "hold_id", "H-9")
        self.c.execute("INSERT INTO holds VALUES (?,?,?,?,NULL,NULL,?)", [hid, invoice_id, code, today, reason])
        if inv.status in (InvoiceStatus.RECEIVED, InvoiceStatus.APPROVED):
            self.c.execute("UPDATE invoices SET status='ON_HOLD' WHERE invoice_id=?", [invoice_id])
        return {"hold_id": hid, "invoice_id": invoice_id, "status": "ON_HOLD"}

    def release_hold(self, invoice_id: str, hold_id: str, reason: str, actor: str, today: str) -> dict:
        self.get_invoice(invoice_id)
        cur = self.c.execute("UPDATE holds SET released_at=?, released_by=?, reason=COALESCE(reason,'') || ' | released: ' || ? "
                             "WHERE hold_id=? AND invoice_id=? AND released_at IS NULL", [today, actor, reason, hold_id, invoice_id])
        if cur.rowcount != 1:
            raise PreconditionFailed(f"No active hold {hold_id} on {invoice_id}")
        remaining = self.c.execute("SELECT COUNT(*) FROM holds WHERE invoice_id=? AND released_at IS NULL", [invoice_id]).fetchone()[0]
        if remaining == 0:
            self.c.execute("UPDATE invoices SET status='APPROVED' WHERE invoice_id=? AND status='ON_HOLD'", [invoice_id])
        status = self.c.execute("SELECT status FROM invoices WHERE invoice_id=?", [invoice_id]).fetchone()[0]
        return {"invoice_id": invoice_id, "hold_id": hold_id, "released": True, "status": status}

    def reject(self, invoice_id: str, reason: str) -> dict:
        inv = self.get_invoice(invoice_id)
        if inv.status in (InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.SCHEDULED):
            raise PreconditionFailed(f"Cannot reject invoice in status {inv.status}")
        self.c.execute("UPDATE invoices SET status='REJECTED', status_reason=? WHERE invoice_id=?", [reason, invoice_id])
        return {"invoice_id": invoice_id, "status": "REJECTED"}

    def update_po_ref(self, invoice_id: str, po_id: str) -> dict:
        self.get_invoice(invoice_id)
        self.c.execute("UPDATE invoices SET po_ref=? WHERE invoice_id=?", [po_id, invoice_id])
        return {"invoice_id": invoice_id, "po_ref": po_id, "note": "Holds re-evaluate on the next match run"}

    def approve_payment(self, invoice_id: str, today: str) -> dict:
        inv = self.get_invoice(invoice_id)
        if inv.holds:
            raise PreconditionFailed("Invoice has active holds")
        if inv.status not in (InvoiceStatus.RECEIVED, InvoiceStatus.APPROVED):
            raise PreconditionFailed(f"Cannot approve invoice in status {inv.status}")
        pid = self._next_id("payments", "payment_id", "PAY-9")
        self.c.execute("INSERT INTO payments VALUES (?,?,?,?,?,NULL,NULL)", [pid, invoice_id, str(inv.total), "SCHEDULED", today])
        self.c.execute("UPDATE invoices SET status='SCHEDULED' WHERE invoice_id=?", [invoice_id])
        return {"invoice_id": invoice_id, "status": "SCHEDULED", "payment_id": pid}

    def create_ticket(self, invoice_id: str, summary: str, assignee_role: str, actor: str, today: str) -> dict:
        self.get_invoice(invoice_id)
        tid = self._next_id("exception_tickets", "ticket_id", "EXC-")
        self.c.execute("INSERT INTO exception_tickets VALUES (?,?,?,?,?,?)", [tid, invoice_id, summary, assignee_role, actor, today])
        return {"ticket_id": tid, "invoice_id": invoice_id}

    def update_vendor(self, vendor_id: str, fields: dict, today: str) -> dict:
        self.get_vendor(vendor_id)
        if "bank_account" in fields and fields["bank_account"]:
            self.c.execute("UPDATE vendors SET bank_account=?, bank_changed_at=? WHERE vendor_id=?",
                           [fields["bank_account"], today, vendor_id])
        if "name" in fields and fields["name"]:
            self.c.execute("UPDATE vendors SET name=? WHERE vendor_id=?", [fields["name"], vendor_id])
        return {"vendor_id": vendor_id, "updated": sorted(k for k, v in fields.items() if v)}


def users_from_db(conn: sqlite3.Connection) -> dict[str, Principal]:
    out = {}
    for r in conn.execute("SELECT * FROM users"):
        out[r["user_id"]] = Principal(user_id=r["user_id"], tenant_id=r["tenant_id"], bu_ids=tuple(json.loads(r["bu_ids"])),
                                      roles=tuple(json.loads(r["roles"])))
    return out
