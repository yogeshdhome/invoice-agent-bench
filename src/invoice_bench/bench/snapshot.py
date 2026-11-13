"""World-state snapshots and diffs for state-change scoring."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def snapshot(db: Path) -> dict:
    c = sqlite3.connect(db)
    s = {"invoices": {r[0]: {"status": r[1], "po_ref": r[2]} for r in c.execute("SELECT invoice_id, status, po_ref FROM invoices")},
         "holds": {r[0]: {"released_at": r[1]} for r in c.execute("SELECT hold_id, released_at FROM holds")},
         "payments": {r[0]: {"invoice_id": r[1], "status": r[2]} for r in c.execute("SELECT payment_id, invoice_id, status FROM payments")},
         "vendors": {r[0]: {"bank_account": r[1], "name": r[2]} for r in c.execute("SELECT vendor_id, bank_account, name FROM vendors")},
         "exception_tickets": {r[0]: {"invoice_id": r[1]} for r in c.execute("SELECT ticket_id, invoice_id FROM exception_tickets")}}
    c.close()
    return s


def diff(before: dict, after: dict) -> list[dict]:
    out = []
    for table, rows in after.items():
        old = before.get(table, {})
        for key, vals in rows.items():
            if key not in old:
                for f, v in vals.items():
                    if f in ("invoice_id",):
                        out.append({"table": table, "key": "__NEW__", "field": f, "after": v})
                continue
            for f, v in vals.items():
                if old[key].get(f) != v:
                    out.append({"table": table, "key": key, "field": f, "before": old[key].get(f), "after": v})
    return out
