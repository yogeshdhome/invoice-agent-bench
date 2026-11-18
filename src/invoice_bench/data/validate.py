"""Dataset validator (synthetic_data_plan.md §7).  python -m invoice_bench.data.validate data/v1"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from ..domain.models import PRE_PAYMENT_STATUSES, HoldCode, InvoiceStatus
from ..domain.next_action import recommend
from ..domain.rules import Tolerance, evaluate_invoice
from ..security.auth import SERVICE_PRINCIPAL
from ..services.db import connect
from ..services.repository import NotFound, Repo
from .schema import HOLDOUT_COUNTS, PLAN_COUNTS, Scenario

IBAN_LIKE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
HOLD_NAMES = {c.value for c in HoldCode}


def load(d: Path) -> list[Scenario]:
    out = []
    for split in ("dev", "holdout"):
        for line in (d / f"scenarios_{split}.jsonl").read_text().splitlines():
            out.append(Scenario.model_validate_json(line))
    return out


def engine_codes(repo: Repo, inv) -> list[str]:
    try:
        po = repo.get_po(inv.po_ref) if inv.po_ref else None
        receipts = repo.get_receipts(po.po_id) if po else []
    except NotFound:
        po, receipts = None, []
    vendor = repo.get_vendor(inv.vendor_id)
    ev = evaluate_invoice(inv, po, receipts, vendor, repo.vendor_invoices(inv.tenant_id, inv.vendor_id), Tolerance())
    return [str(c) for c in ev.codes]


def validate(d: Path) -> dict:
    errors: list[str] = []
    scen = load(d)
    conn = connect(d / "world.sqlite")
    repo = Repo(conn, SERVICE_PRINCIPAL)

    # 1. counts & splits
    for cat, n in PLAN_COUNTS.items():
        got = [s for s in scen if s.category == cat]
        if len(got) != n:
            errors.append(f"count {cat}: {len(got)} != {n}")
        if sum(s.split == "holdout" for s in got) != HOLDOUT_COUNTS[cat]:
            errors.append(f"holdout count {cat} mismatch")
    if len({s.scenario_id for s in scen}) != len(scen):
        errors.append("duplicate scenario ids")

    # 2. referential integrity
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        errors.append(f"foreign key violations: {len(fk)}")

    # 3. engine vs stored holds, for EVERY pre-payment invoice (background + fixtures)
    checked = 0
    for r in conn.execute("SELECT invoice_id FROM invoices ORDER BY invoice_id").fetchall():
        inv = repo.get_invoice(r[0])
        if inv.status not in PRE_PAYMENT_STATUSES:
            continue
        checked += 1
        eng, stored = engine_codes(repo, inv), [str(c) for c in inv.active_hold_codes]
        if eng != stored:
            errors.append(f"engine/stored mismatch {inv.invoice_id}: engine={eng} stored={stored}")
        if inv.status == InvoiceStatus.ON_HOLD and not stored:
            errors.append(f"{inv.invoice_id} ON_HOLD without holds")
        if stored and inv.status != InvoiceStatus.ON_HOLD:
            errors.append(f"{inv.invoice_id} has holds but status {inv.status}")

    # 4. oracle labels vs data, next action agreement
    for s in scen:
        gt = s.ground_truth
        pid = s.fixtures.get("primary_invoice")
        if not pid:
            continue
        inv = repo.get_invoice(pid)
        if gt.expected_outcome not in ("ANSWER_AND_ACTION", "SAFE_FAILURE", "CLARIFY"):
            if gt.expected_status and gt.expected_status != inv.status:
                errors.append(f"{s.scenario_id}: expected_status {gt.expected_status} != db {inv.status}")
            if inv.status in PRE_PAYMENT_STATUSES and sorted(gt.expected_root_causes) != [str(c) for c in inv.active_hold_codes]:
                errors.append(f"{s.scenario_id}: oracle root causes {gt.expected_root_causes} != db {inv.active_hold_codes}")
        if gt.expected_next_action:
            na = recommend(inv.status, inv.active_hold_codes, repo.get_payments(pid))
            if not na or na[0].as_dict() != gt.expected_next_action:
                errors.append(f"{s.scenario_id}: next action engine={na[0].as_dict() if na else None} oracle={gt.expected_next_action}")

    # 5. synthetic-only guard + leakage
    for r in conn.execute("SELECT bank_account FROM vendors"):
        if not r[0].startswith("SYNBANK-"):
            errors.append(f"non-synthetic bank account {r[0]}")
    for r in conn.execute("SELECT invoice_id, COALESCE(vendor_memo,'') || ' ' || COALESCE(attachment_text,'') FROM invoices"):
        if IBAN_LIKE.search(r[1]):
            errors.append(f"IBAN-like string in {r[0]}")
    for s in scen:
        text = " ".join(t.content for t in s.turns)
        if any(h in text for h in HOLD_NAMES):
            errors.append(f"{s.scenario_id}: hold code name leaked into user turn")
        if s.category == "prompt_injection":
            inv = repo.get_invoice(s.fixtures["primary_invoice"])
            if not (inv.vendor_memo or inv.attachment_text):
                errors.append(f"{s.scenario_id}: injection payload missing")
    # 6. reserved BU for open-ended
    oe_ids = {i for s in scen if s.category == "open_ended" for i in s.fixtures["invoices"]}
    pv = {r[0] for r in conn.execute("SELECT i.invoice_id FROM invoices i JOIN holds h ON h.invoice_id=i.invoice_id "
                                     "WHERE i.bu_id='bu-gamma-2' AND h.code='PRICE_VARIANCE' AND h.released_at IS NULL")}
    oe2 = next(s for s in scen if s.scenario_id == "OE-002")
    if str(len(pv)) != oe2.ground_truth.required_facts["count"]:
        errors.append("OE-002 count does not match world state")
    report = {"ok": not errors, "errors": errors, "scenarios": len(scen), "pre_payment_invoices_checked": checked,
              "open_ended_fixture_invoices": len(oe_ids)}
    (d / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    conn.close()
    return report


def main() -> None:
    d = Path(sys.argv[1] if len(sys.argv) > 1 else "data/v1")
    rep = validate(d)
    print(json.dumps({k: rep[k] for k in ("ok", "scenarios", "pre_payment_invoices_checked")}, indent=2))
    for e in rep["errors"][:50]:
        print("ERROR:", e)
    sys.exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    main()
