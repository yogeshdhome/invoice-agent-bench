"""SQLite schema for the synthetic world. Decimals stored as TEXT for exactness."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE business_units(bu_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id), name TEXT NOT NULL);
CREATE TABLE users(user_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  bu_ids TEXT NOT NULL, roles TEXT NOT NULL, display_name TEXT NOT NULL);
CREATE TABLE vendors(vendor_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id), name TEXT NOT NULL,
  status TEXT NOT NULL, bank_account TEXT NOT NULL, bank_changed_at TEXT);
CREATE TABLE purchase_orders(po_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  bu_id TEXT NOT NULL REFERENCES business_units(bu_id), vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  status TEXT NOT NULL, currency TEXT NOT NULL, total_amount TEXT NOT NULL, consumed_amount TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE po_lines(po_line_id TEXT PRIMARY KEY, po_id TEXT NOT NULL REFERENCES purchase_orders(po_id), line_no INTEGER NOT NULL,
  sku TEXT NOT NULL, qty INTEGER NOT NULL, unit_price TEXT NOT NULL);
CREATE TABLE goods_receipts(gr_id TEXT PRIMARY KEY, po_id TEXT NOT NULL REFERENCES purchase_orders(po_id), received_at TEXT NOT NULL);
CREATE TABLE gr_lines(gr_line_id TEXT PRIMARY KEY, gr_id TEXT NOT NULL REFERENCES goods_receipts(gr_id),
  po_line_id TEXT NOT NULL REFERENCES po_lines(po_line_id), qty_received INTEGER NOT NULL);
CREATE TABLE invoices(invoice_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  bu_id TEXT NOT NULL REFERENCES business_units(bu_id), vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_ref TEXT, vendor_invoice_no TEXT NOT NULL, invoice_date TEXT NOT NULL, currency TEXT NOT NULL,
  subtotal TEXT NOT NULL, tax TEXT NOT NULL, total TEXT NOT NULL, status TEXT NOT NULL, status_reason TEXT,
  vendor_memo TEXT, attachment_text TEXT);
CREATE TABLE invoice_lines(invoice_line_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
  po_line_id TEXT REFERENCES po_lines(po_line_id), sku TEXT NOT NULL, qty INTEGER NOT NULL, unit_price TEXT NOT NULL, amount TEXT NOT NULL);
CREATE TABLE holds(hold_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id), code TEXT NOT NULL,
  created_at TEXT NOT NULL, released_at TEXT, released_by TEXT, reason TEXT);
CREATE TABLE payments(payment_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id), amount TEXT NOT NULL,
  status TEXT NOT NULL, scheduled_date TEXT, paid_date TEXT, failure_reason TEXT);
CREATE TABLE exception_tickets(ticket_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
  summary TEXT NOT NULL, assignee_role TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE approvals(approval_id TEXT PRIMARY KEY, action_hash TEXT NOT NULL UNIQUE, tool TEXT NOT NULL, args_json TEXT NOT NULL,
  requester TEXT NOT NULL, approver TEXT, decision TEXT, expires_at TEXT NOT NULL, decided_at TEXT);
CREATE TABLE action_log(idempotency_key TEXT PRIMARY KEY, action TEXT NOT NULL, target_id TEXT NOT NULL, args_hash TEXT NOT NULL,
  result_json TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE audit_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts TEXT NOT NULL, principal TEXT NOT NULL,
  event_type TEXT NOT NULL, rule_id TEXT, payload_hash TEXT, evidence_refs TEXT);
CREATE INDEX ix_inv_vendor ON invoices(tenant_id, vendor_id);
CREATE INDEX ix_inv_status ON invoices(tenant_id, status);
CREATE INDEX ix_holds_inv ON holds(invoice_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


def canonical_dump_sha256(conn: sqlite3.Connection) -> str:
    import hashlib
    h = hashlib.sha256()
    for line in conn.iterdump():
        h.update(line.encode())
    return h.hexdigest()
